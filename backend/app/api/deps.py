from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User
from app.repositories.user import UserRepository
from app.security.jwt_tokens import decode_access_token

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
    db: DbSession,
    settings: SettingsDep,
) -> Optional[User]:
    if not credentials or not credentials.credentials:
        return None
    token = credentials.credentials
    try:
        payload = decode_access_token(token, settings.jwt_secret_key, settings.jwt_algorithm)
        sub = payload.get("sub")
        if sub is None:
            return None
        uid = int(sub)
    except (JWTError, ValueError, TypeError):
        return None
    repo = UserRepository(db)
    return await repo.get_by_id(uid)


async def get_current_user(
    user: Annotated[Optional[User], Depends(get_optional_user)],
) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


OptionalUser = Annotated[Optional[User], Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]
