from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.errors import AppError
from app.main import app
from app.models import User
from app.schemas.identity import UserUpdate
from app.security import verify_password
from app.services import identity


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class UserDb:
    def __init__(self, users: list[User]):
        self.users = users
        self.commits = 0

    async def scalars(self, statement):
        text = str(statement)
        if "ORDER BY users.created_at ASC" in text:
            return ScalarRows(self.users)
        return ScalarRows([user for user in self.users if user.system_role == "admin" and user.is_active])

    async def scalar(self, _statement):
        user_id = next(iter(_statement.compile().params.values()), None)
        return next((user for user in self.users if user.id == user_id), None)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _row):
        return None


class AuthDb:
    def __init__(self, user: User):
        self.user = user

    async def scalar(self, _statement):
        return self.user

    async def commit(self):
        return None


def make_user(user_id: str, *, role: str = "user", active: bool = True, password_hash: str = "x") -> User:
    return User(id=user_id, username=user_id, password_hash=password_hash, name=user_id, email=f"{user_id}@example.test", system_role=role, is_active=active)


def test_admin_can_list_users_without_password_hash() -> None:
    admin = make_user("admin", role="admin")
    member = make_user("member")

    async def override_user():
        return admin

    async def override_db():
        yield UserDb([admin, member])

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/auth/users")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert [row["username"] for row in response.json()["data"]] == ["admin", "member"]
    assert "password_hash" not in response.text


def test_non_admin_user_list_is_forbidden() -> None:
    actor = make_user("member")

    async def override_user():
        return actor

    app.dependency_overrides[get_current_user] = override_user
    try:
        response = TestClient(app).get("/api/auth/users")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


@pytest.mark.asyncio
async def test_disabling_self_is_rejected() -> None:
    actor = make_user("admin", role="admin")
    with pytest.raises(AppError, match="当前登录用户") as caught:
        await identity.update_user(UserDb([actor]), actor, actor.id, UserUpdate(is_active=False))
    assert caught.value.code == "CANNOT_DISABLE_SELF"


@pytest.mark.asyncio
async def test_disabling_last_active_admin_is_rejected() -> None:
    actor = make_user("admin", role="admin")
    target = make_user("target", role="admin")
    db = UserDb([target])
    with pytest.raises(AppError) as caught:
        await identity.update_user(db, actor, target.id, UserUpdate(is_active=False))
    assert caught.value.code == "LAST_ADMIN_PROTECTED"
    assert db.commits == 0


@pytest.mark.asyncio
async def test_demoting_last_active_admin_is_rejected() -> None:
    actor = make_user("admin", role="admin")
    target = make_user("target", role="admin")
    with pytest.raises(AppError) as caught:
        await identity.update_user(UserDb([target]), actor, target.id, UserUpdate(system_role="user"))
    assert caught.value.code == "LAST_ADMIN_PROTECTED"


@pytest.mark.asyncio
async def test_reset_password_invalidates_old_password() -> None:
    old_password = "old-password-123"
    new_password = "new-password-456"
    actor = make_user("admin", role="admin")
    target = make_user("target", password_hash=identity.hash_password(old_password))
    db = UserDb([actor, target])
    updated = await identity.update_user(db, actor, target.id, UserUpdate(password=new_password))
    assert verify_password(old_password, updated.password_hash) is False
    assert verify_password(new_password, updated.password_hash) is True
    assert old_password not in updated.password_hash
    with pytest.raises(AppError) as caught:
        await identity.authenticate(AuthDb(updated), updated.username, old_password)
    assert caught.value.code == "AUTH_INVALID_CREDENTIALS"
    assert await identity.authenticate(AuthDb(updated), updated.username, new_password) is updated


@pytest.mark.asyncio
async def test_missing_user_returns_not_found() -> None:
    actor = make_user("admin", role="admin")
    db = UserDb([actor])
    with pytest.raises(AppError) as caught:
        await identity.update_user(db, actor, "missing", UserUpdate(name="New name"))
    assert caught.value.code == "USER_NOT_FOUND"
