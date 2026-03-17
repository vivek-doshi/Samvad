from datetime import datetime, timedelta, timezone
import logging
import os

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-THIS-IN-PRODUCTION")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
	return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed: str) -> bool:
	return pwd_context.verify(plain_password, hashed)


def create_access_token(data: dict) -> str:
	now = datetime.now(timezone.utc)
	to_encode = data.copy()
	to_encode["exp"] = now + timedelta(minutes=EXPIRE_MINUTES)
	to_encode["iat"] = now
	return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
	try:
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		return payload
	except JWTError as exc:
		if "expired" in str(exc).lower():
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Token expired",
			) from exc
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid token",
		) from exc


def get_user_id_from_token(token: str) -> str:
	payload = decode_token(token)
	user_id = payload.get("sub")
	if not user_id:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid token payload",
		)
	return user_id
