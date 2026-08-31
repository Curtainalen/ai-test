from fastapi import APIRouter, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.identity import LoginRequest, RegisterRequest, UserCreate
from app.security import create_access_token
from app.services import identity

router = APIRouter(prefix="/auth", tags=["auth"])


def user_view(user) -> dict:
    return {"id": user.id, "username": user.username, "name": user.name, "email": user.email, "system_role": user.system_role}


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
