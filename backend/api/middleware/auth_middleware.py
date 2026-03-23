from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
# Note 1: HTTPBearer is a FastAPI security scheme that reads the 'Authorization'
# header from the request and extracts the token from 'Bearer <token>'. It
# raises a 403 automatically if the header is missing or malformed.

from backend.security.auth import decode_token, get_user_id_from_token

# Note 2: HTTPBearer() creates a reusable dependency object. FastAPI's dependency
# injection (Depends) calls this automatically for any route that declares
# 'user_id: str = Depends(get_current_user_id)' — no boilerplate in each route.
security = HTTPBearer()


async def get_current_user_id(
	credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
	# Note 3: credentials.credentials is just the raw token string (the part after
	# "Bearer "). We pass it to get_user_id_from_token() which validates the
	# signature, checks expiry, and extracts the 'sub' (user UUID) claim.
	# If the token is invalid or expired, get_user_id_from_token raises HTTPException
	# which FastAPI converts into a 401 response automatically.
	token = credentials.credentials
	return get_user_id_from_token(token)
