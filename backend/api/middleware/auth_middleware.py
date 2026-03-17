from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.security.auth import decode_token, get_user_id_from_token

security = HTTPBearer()


async def get_current_user_id(
	credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
	token = credentials.credentials
	return get_user_id_from_token(token)
