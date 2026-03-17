import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.api.middleware.auth_middleware import get_current_user_id
from backend.security.auth import EXPIRE_MINUTES, create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
	username: str
	password: str


class UserResponse(BaseModel):
	user_id: str
	username: str
	display_name: str
	role: str


class LoginResponse(BaseModel):
	access_token: str
	token_type: str = "bearer"
	expires_in: int
	user: UserResponse


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, payload: LoginRequest):
	db_client = request.app.state.db
	username = payload.username.lower().strip()

	user = await db_client.fetchone(
		"SELECT * FROM users WHERE username = ?",
		(username,),
	)

	if not user:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid credentials",
		)

	if user["is_active"] == 0:
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
