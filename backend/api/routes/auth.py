import uuid
from datetime import datetime, timezone
# Note 1: uuid generates globally unique identifiers (UUIDs). We use uuid4()
# which creates random UUIDs — no predictable sequence that an attacker could
# enumerate to guess other users' IDs or audit log entries.
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
# Note 2: Pydantic BaseModel validates and parses incoming JSON request bodies.
# When a POST request arrives, FastAPI automatically parses the JSON body into
# the declared model, validates field types and constraints, and returns a 422
# error if validation fails — before any handler code runs.

from backend.api.middleware.auth_middleware import get_current_user_id
from backend.security.auth import EXPIRE_MINUTES, create_access_token, verify_password

# Note 3: prefix="/api/auth" means every route in this router is mounted at
# /api/auth/... (e.g. /api/auth/login, /api/auth/logout, /api/auth/me).
# tags=["auth"] groups these endpoints together in the OpenAPI docs (/docs).
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
	# Note 4: These Pydantic fields define what the JSON body must contain.
	# If either field is missing from the request JSON, FastAPI returns a 422
	# error automatically, before the handler function is even called.
	username: str
	password: str


class UserResponse(BaseModel):
	user_id: str
	username: str
	display_name: str
	role: str
	# Note 5: UserResponse is the shape of user data returned to the frontend.
	# It deliberately omits password_hash and other internal fields — never
	# include sensitive DB fields in API responses.


class LoginResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	# Note 6: expires_in follows the OAuth2 convention: seconds until the token
	# expires. The frontend uses this to schedule token refresh or logout.
	expires_in: int
	user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, payload: LoginRequest):
	# Note 7: request.app.state.db is the shared DBClient stored at startup.
	# FastAPI passes the 'request' object for us to access shared state —
	# this is the standard way to inject dependencies without global variables.
	db_client = request.app.state.db
	# Note 8: .lower().strip() normalises the username before lookup.
	# This prevents "Admin" and "admin" being treated as different users.
	username = payload.username.lower().strip()

	user = await db_client.fetchone(
		"SELECT * FROM users WHERE username = ?",
		(username,),
	)

	if not user:
		# Note 9: We return the same error message for "user not found" AND
		# "wrong password" (below). Returning different errors would let an
		# attacker enumerate valid usernames by observing error messages.
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid credentials",
		)

	if user["is_active"] == 0:
		# Note 10: Disabled accounts get a 403 Forbidden (not 401 Unauthorized).
		# 403 means "I know who you are but you are not allowed in". This gives
		# a better user experience than a generic "invalid credentials" message.
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Account disabled",
		)

	if not verify_password(payload.password, user["password_hash"]):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid credentials",
		)

	now = datetime.now(timezone.utc).isoformat()
	# Note 11: timezone.utc ensures the timestamp is stored as UTC, not local time.
	# Always use UTC in the database — let the frontend convert to local time zones.

	await db_client.execute(
		"UPDATE users SET last_login_at = ? WHERE user_id = ?",
		(now, user["user_id"]),
	)

	await db_client.execute(
		"""
		INSERT INTO audit_log
		(log_id, user_id, session_id, event_type, severity, message, details, created_at)
		VALUES (?, ?, NULL, ?, ?, ?, NULL, ?)
		""",
		# Note 12: str(uuid.uuid4()) generates a random UUID string as the log_id
		# primary key. This is done in Python (not SQL) because SQLite doesn't have
		# a built-in UUID function. The NULL session_id means this event is not tied
		# to a specific conversation session.
		(
			str(uuid.uuid4()),
			user["user_id"],
			"login_success",
			"info",
			f"Login from username {user['username']}",
			now,
		),
	)

	access_token = create_access_token(
		{
			# Note 13: 'sub' (subject) is the standard JWT claim for the entity
			# the token represents. We use the user's UUID (not username) as the
			# subject so that a username change doesn't invalidate existing tokens.
			"sub": user["user_id"],
			"username": user["username"],
			"role": user["role"],
		}
	)

	return LoginResponse(
		access_token=access_token,
		expires_in=EXPIRE_MINUTES * 60,
		user=UserResponse(
			user_id=user["user_id"],
			username=user["username"],
			display_name=user["display_name"],
			role=user["role"],
		),
	)


@router.post("/logout")
async def logout(request: Request, user_id: str = Depends(get_current_user_id)):
	db_client = request.app.state.db
	now = datetime.now(timezone.utc).isoformat()

	await db_client.execute(
		"""
		INSERT INTO audit_log
		(log_id, user_id, session_id, event_type, severity, message, details, created_at)
		VALUES (?, ?, NULL, ?, ?, ?, NULL, ?)
		""",
		(
			str(uuid.uuid4()),
			user_id,
			"logout",
			"info",
			"User logged out",
			now,
		),
	)

	return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def me(request: Request, user_id: str = Depends(get_current_user_id)):
	db_client = request.app.state.db
	user = await db_client.fetchone(
		"SELECT user_id, username, display_name, role FROM users WHERE user_id = ?",
		(user_id,),
	)

	if not user:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

	return UserResponse(
		user_id=user["user_id"],
		username=user["username"],
		display_name=user["display_name"],
		role=user["role"],
	)
