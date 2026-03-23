from datetime import datetime, timedelta, timezone
import logging
import os

from fastapi import HTTPException, status
from jose import JWTError, jwt
# Note 1: python-jose is a JWT (JSON Web Token) library. JWTs are the standard
# way to implement stateless authentication in REST APIs. The server creates a
# signed token on login; the client sends it back on every subsequent request
# so the server can verify identity without querying the database every time.
from passlib.context import CryptContext
# Note 2: passlib.CryptContext handles password hashing with bcrypt. Passwords
# should NEVER be stored as plain text — bcrypt stores a one-way hash plus a
# random salt, so two identical passwords produce different hashes, protecting
# users even if the database is compromised.

logger = logging.getLogger(__name__)

# Note 3: SECRET_KEY signs and verifies JWTs. In production, this MUST be
# replaced with a long random string (e.g. 'openssl rand -hex 32'). If the
# secret leaks, attackers can forge tokens for any user. The environment
# variable approach keeps it out of version control.
# Security note: The default "CHANGE-THIS-IN-PRODUCTION" is intentionally
# obvious. Consider raising a startup ValueError if SAMVAD_ENV=production
# and the key still has the default value to prevent accidental deployment.
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE-THIS-IN-PRODUCTION")
# Note 4: HS256 (HMAC-SHA256) is a symmetric signing algorithm — the same
# secret key is used to sign and verify. RS256 (asymmetric) is preferred for
# distributed systems where multiple services need to verify tokens.
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Note 5: 480 minutes = 8 hours. A typical work-day session length. Shorter
# tokens are more secure (less exposure if stolen) but annoy users with frequent
# re-logins. Balance security and usability for your specific use case.
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
	# Note 6: pwd_context.hash() uses bcrypt to generate a salted hash. Each call
	# produces a DIFFERENT hash even for the same input (due to the random salt),
	# so rainbow table attacks are ineffective. Only called when creating or
	# updating passwords — never during the login check.
	return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed: str) -> bool:
	# Note 7: pwd_context.verify() hashes plain_password with the SAME salt
	# embedded in 'hashed', then compares results. Uses constant-time comparison
	# to prevent timing-based attacks that could otherwise detect correct passwords.
	return pwd_context.verify(plain_password, hashed)


def create_access_token(data: dict) -> str:
	# Note 8: We copy 'data' to avoid mutating the caller's dict. Standard JWT
	# claims 'exp' (expiry) and 'iat' (issued-at) are added so the token carries
	# its own validity window — no server-side session storage is needed.
	now = datetime.now(timezone.utc)
	to_encode = data.copy()
	to_encode["exp"] = now + timedelta(minutes=EXPIRE_MINUTES)
	to_encode["iat"] = now
	return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
	try:
		# Note 9: jwt.decode() verifies the signature and checks expiry automatically.
		# Passing algorithms=[ALGORITHM] as a list (not a string) prevents algorithm
		# confusion attacks where an attacker swaps HS256 for 'none' to forge tokens.
		payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
		return payload
	except JWTError as exc:
		if "expired" in str(exc).lower():
			# Note 10: We distinguish expired from invalid so the frontend can show
			# "session expired, please log in again" instead of a generic error.
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
	# Note 11: 'sub' (subject) is the standard JWT claim for the principal the
	# token represents — here it stores the user's UUID. Checking for None
	# defends against malformed tokens that pass signature verification but
	# lack required claims.
	if not user_id:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid token payload",
		)
	return user_id
