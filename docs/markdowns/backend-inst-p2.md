You are working on Samvad — a locally-hosted finance AI interface.
Backend is FastAPI, Python 3.11, async throughout.
Database is SQLite via aiosqlite. Schema is already defined in
backend/db/schema.sql — read it before writing any code.

=============================================================
FILE 1: backend/security/auth.py
=============================================================

PURPOSE: bcrypt password hashing + JWT issue and verify.
This is security-critical code — be precise.

IMPORTS:
  from datetime import datetime, timedelta, timezone
  from passlib.context import CryptContext
  from jose import JWTError, jwt
  import os, logging

Constants (from environment, not hardcoded):
  SECRET_KEY    = os.getenv("SECRET_KEY", "CHANGE-THIS-IN-PRODUCTION")
  ALGORITHM     = os.getenv("JWT_ALGORITHM", "HS256")
  EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

FUNCTIONS:

  hash_password(plain_password: str) -> str
    return pwd_context.hash(plain_password)

  verify_password(plain_password: str, hashed: str) -> bool
    return pwd_context.verify(plain_password, hashed)

  create_access_token(data: dict) -> str
    Make a copy of data
    Add "exp" claim: datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    Add "iat" claim: datetime.now(timezone.utc)
    return jwt.encode(copy, SECRET_KEY, algorithm=ALGORITHM)

  decode_token(token: str) -> dict
    Decode and return payload dict
    Raise HTTPException(401, "Token expired") if JWTError with "expired" in str
    Raise HTTPException(401, "Invalid token") for any other JWTError

  get_user_id_from_token(token: str) -> str
    Call decode_token(token)
    Return payload["sub"]
    Raise HTTPException(401, "Invalid token payload") if "sub" missing

=============================================================
FILE 2: backend/api/middleware/auth_middleware.py
=============================================================

PURPOSE: FastAPI dependency that validates JWT on protected routes.

  from fastapi import Depends, HTTPException, status
  from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
  from backend.security.auth import decode_token, get_user_id_from_token

  security = HTTPBearer()

  async def get_current_user_id(
      credentials: HTTPAuthorizationCredentials = Depends(security)
  ) -> str:
    token = credentials.credentials
    return get_user_id_from_token(token)

  This is a FastAPI dependency — inject with:
    Depends(get_current_user_id)
  It returns the user_id string from the JWT "sub" claim.

=============================================================
FILE 3: backend/api/routes/auth.py
=============================================================

ROUTER: APIRouter(prefix="/api/auth", tags=["auth"])

REQUEST/RESPONSE MODELS:

  class LoginRequest(BaseModel):
    username: str
    password: str

  class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int              # seconds
    user: UserResponse

  class UserResponse(BaseModel):
    user_id: str
    username: str
    display_name: str
    role: str

ENDPOINTS:

  POST /api/auth/login
    - Get db_client from request.app.state.db
    - Query users table: SELECT * FROM users WHERE username = ?
      Use: username.lower().strip()
    - If no user found: raise HTTPException(401, "Invalid credentials")
      IMPORTANT: same error message whether user not found OR wrong password
      (prevents username enumeration)
    - If user.is_active == 0: raise HTTPException(403, "Account disabled")
    - verify_password(request.password, user.password_hash)
    - If fails: raise HTTPException(401, "Invalid credentials")
    - Update last_login_at in users table
    - Write audit_log entry:
        event_type="login_success", severity="info",
        user_id=user.user_id,
        message=f"Login from username {user.username}"
    - Create JWT with: {"sub": user.user_id, "username": user.username,
                        "role": user.role}
    - Return LoginResponse

  POST /api/auth/logout
    - Requires auth: Depends(get_current_user_id)
    - Write audit_log entry: event_type="logout"
    - Return {"message": "Logged out successfully"}
    - Note: JWT is stateless — actual invalidation not needed for MVP.
      Client discards the token.

  GET /api/auth/me
    - Requires auth: Depends(get_current_user_id)
    - Fetch user from DB by user_id
    - Return UserResponse

=============================================================
FILE 4: backend/api/routes/sessions.py
=============================================================

ROUTER: APIRouter(prefix="/api/sessions", tags=["sessions"])

RESPONSE MODELS:

  class SessionResponse(BaseModel):
    session_id: str
    title: str
    status: str
    total_turns: int
    domain_last: str | None
    created_at: str
    last_active_at: str

  class TurnResponse(BaseModel):
    turn_id: str
    session_id: str
    turn_number: int
    role: str
    content: str
    domain: str | None
    sources_cited: list | None  # parsed from JSON string
    created_at: str

  class UpdateSessionRequest(BaseModel):
    title: str | None = None

ENDPOINTS — all require Depends(get_current_user_id):

  GET /api/sessions
    - Query v_session_history view filtered by user_id
    - Return list[SessionResponse]
    - Ordered by last_active_at DESC

  POST /api/sessions
    - Close any currently active session for this user:
        UPDATE sessions SET is_active=0, status='closed',
        closed_at=now WHERE user_id=? AND is_active=1
    - Generate new session_id: str(uuid4())
    - Auto-generate title: "Chat — {datetime now as DD Mon HH:MM}"
    - INSERT new session with is_active=1, status='active'
    - Return SessionResponse of newly created session

  GET /api/sessions/{session_id}
    - Verify session belongs to current user_id (403 if not)
    - Return SessionResponse

  PATCH /api/sessions/{session_id}
    - Verify session belongs to current user_id (403 if not)
    - Update title if provided in request body
    - Return updated SessionResponse

  DELETE /api/sessions/{session_id}
    - Verify session belongs to current user_id (403 if not)
    - UPDATE status='archived', is_active=0
    - Do NOT delete — preserve history
    - Return {"message": "Session archived"}

  GET /api/sessions/{session_id}/turns
    - Verify session belongs to current user_id (403 if not)
    - SELECT * FROM turns WHERE session_id=? ORDER BY turn_number ASC
    - Parse sources_cited JSON string to list for each turn
    - Return list[TurnResponse]

=============================================================
FILE 5: backend/db/db_client.py
=============================================================

PURPOSE: Async SQLite wrapper. Sets required PRAGMAs on every
connection. Single connection pool for the application.

IMPORTS:
  import aiosqlite, sqlite3, json, logging
  from pathlib import Path
  from contextlib import asynccontextmanager

class DBClient:

  __init__(self, db_path: str)
    self.db_path = db_path
    self._conn: aiosqlite.Connection | None = None

  async def connect(self) -> None
    Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    self._conn = await aiosqlite.connect(self.db_path)
    self._conn.row_factory = aiosqlite.Row
    await self._conn.execute("PRAGMA foreign_keys = ON")
    await self._conn.execute("PRAGMA journal_mode = WAL")
    await self._conn.execute("PRAGMA synchronous = NORMAL")
    await self._conn.commit()

  async def close(self) -> None
    if self._conn:
      await self._conn.close()
      self._conn = None

  async def init_schema(self) -> None
    schema_path = Path(__file__).parent / "schema.sql"
    schema = schema_path.read_text()
    await self._conn.executescript(schema)
    await self._conn.commit()

  async def fetchone(self, sql: str, params: tuple = ()) -> dict | None
    async with self._conn.execute(sql, params) as cur:
      row = await cur.fetchone()
      return dict(row) if row else None

  async def fetchall(self, sql: str, params: tuple = ()) -> list[dict]
    async with self._conn.execute(sql, params) as cur:
      rows = await cur.fetchall()
      return [dict(row) for row in rows]

  async def execute(self, sql: str, params: tuple = ()) -> int
    async with self._conn.execute(sql, params) as cur:
      await self._conn.commit()
      return cur.lastrowid

  async def executemany(self, sql: str, params_list: list) -> None
    await self._conn.executemany(sql, params_list)
    await self._conn.commit()

  @asynccontextmanager
  async def transaction(self):
    async with self._conn.cursor() as cur:
      try:
        yield cur
        await self._conn.commit()
      except Exception:
        await self._conn.rollback()
        raise

=============================================================
FILE 6: backend/scripts/setup_first_user.py
=============================================================

PURPOSE: Interactive CLI script to create the first admin user.
Run once after first deploy: python backend/scripts/setup_first_user.py

  import asyncio, sys, uuid
  from datetime import datetime, timezone
  from pathlib import Path

  # Add project root to path
  sys.path.insert(0, str(Path(__file__).parent.parent.parent))

  from backend.db.db_client import DBClient
  from backend.security.auth import hash_password
  import os
  from dotenv import load_dotenv
  load_dotenv()

  async def main():
    db_path = os.getenv("SQLITE_PATH", "runtime/sqlite/samvad.db")
    db = DBClient(db_path)
    await db.connect()
    await db.init_schema()

    print("\n=== Samvad — Create First User ===\n")

    existing = await db.fetchone("SELECT COUNT(*) as cnt FROM users")
    if existing and existing["cnt"] > 0:
      print(f"Users already exist ({existing['cnt']} found).")
      confirm = input("Add another user? [y/N]: ").strip().lower()
      if confirm != 'y':
        print("Exiting.")
        return

    username     = input("Username: ").strip().lower()
    display_name = input("Display name: ").strip()
    password     = input("Password (min 8 chars): ").strip()
    role         = input("Role [user/admin] (default: admin): ").strip() or "admin"

    if len(password) < 8:
      print("Password too short. Minimum 8 characters.")
      return

    user_id       = str(uuid.uuid4())
    password_hash = hash_password(password)
    now           = datetime.now(timezone.utc).isoformat()

    await db.execute(
      """INSERT INTO users
         (user_id, username, display_name, password_hash, role, is_active, created_at)
         VALUES (?,?,?,?,?,1,?)""",
      (user_id, username, display_name, password_hash, role, now)
    )

    print(f"\nUser created successfully.")
    print(f"  user_id : {user_id}")
    print(f"  username: {username}")
    print(f"  role    : {role}")
    print(f"\nYou can now log in to Samvad at http://localhost:4200\n")

    await db.close()

  asyncio.run(main())

=============================================================
ALSO UPDATE: backend/main.py
=============================================================

Find the lifespan startup section.
Add db initialisation AFTER config loading, BEFORE llm_client:

  from backend.db.db_client import DBClient
  from backend.api.routes import auth as auth_router
  from backend.api.routes import sessions as sessions_router
  from backend.api.middleware.auth_middleware import get_current_user_id

  # In lifespan startup:
  db_path = os.getenv("SQLITE_PATH", "runtime/sqlite/samvad.db")
  db = DBClient(db_path)
  await db.connect()
  await db.init_schema()
  app.state.db = db
  logger.info("SQLite connected: %s", db_path)

  # In lifespan shutdown:
  await app.state.db.close()

  # Add routers (after existing chat router):
  app.include_router(auth_router.router)
  app.include_router(sessions_router.router)