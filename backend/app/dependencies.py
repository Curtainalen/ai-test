from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.errors import AppError
from app.models import User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: DbSession) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError("AUTH_REQUIRED", "请先登录", 401)
    user = await db.get(User, decode_access_token(credentials.credentials))
    if user is None or not user.is_active:
        raise AppError("AUTH_INVALID_TOKEN", "登录状态无效或账号已停用", 401)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
