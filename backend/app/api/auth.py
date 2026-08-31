from fastapi import APIRouter, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.identity import LoginRequest, RegisterRequest, UserCreate, UserUpdate
from app.security import create_access_token
from app.services import identity

router = APIRouter(prefix="/auth", tags=["auth"])


def user_view(user) -> dict:
    return {"id": user.id, "username": user.username, "name": user.name, "email": user.email, "system_role": user.system_role}


def managed_user_view(user) -> dict:
    return {
        **user_view(user),
        "is_active": user.is_active,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, request: Request, db: DbSession):
    user = await identity.register_first_user(db, data)
    return success({"user": user_view(user), "access_token": create_access_token(user.id), "token_type": "bearer"}, request.state.trace_id)


@router.post("/login")
async def login(data: LoginRequest, request: Request, db: DbSession):
    user = await identity.authenticate(db, data.username, data.password)
    return success({"user": user_view(user), "access_token": create_access_token(user.id), "token_type": "bearer"}, request.state.trace_id)


@router.get("/me")
async def me(user: CurrentUser, request: Request):
    return success(user_view(user), request.state.trace_id)


@router.post("/users", status_code=201)
async def create_user(data: UserCreate, user: CurrentUser, request: Request, db: DbSession):
    return success(user_view(await identity.create_user(db, user, data)), request.state.trace_id)


@router.get("/users")
async def list_users(user: CurrentUser, request: Request, db: DbSession):
    return success([managed_user_view(row) for row in await identity.list_users(db, user)], request.state.trace_id)


@router.patch("/users/{user_id}")
async def update_user(user_id: str, data: UserUpdate, user: CurrentUser, request: Request, db: DbSession):
    return success(managed_user_view(await identity.update_user(db, user, user_id, data)), request.state.trace_id)
