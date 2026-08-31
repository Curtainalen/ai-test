from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models import User
from app.services import identity


def test_projects_and_users_have_no_delete_routes() -> None:
    with TestClient(app) as client:
        for path in ("/api/projects", "/api/projects/project-1", "/api/auth/users/user-1"):
            response = client.delete(path)
            assert response.status_code in {404, 405}
            assert response.json()["success"] is False


def test_project_create_and_list_contracts_remain_available(monkeypatch) -> None:
    actor = User(id="admin", username="admin", password_hash="x", system_role="admin")
    project = type("ProjectRow", (), {"id": "project-1", "name": "Core", "description": "", "owner_id": actor.id, "status": "active", "revision": 1, "created_at": __import__("datetime").datetime.now()})()

    async def override_user():
        return actor

    async def override_db():
        yield object()

    async def create_project(_db, _actor, _data):
        return project

    async def list_projects(_db, _actor):
        return [(project, "Owner")]

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(identity, "create_project", create_project)
    monkeypatch.setattr(identity, "list_projects", list_projects)
    try:
        with TestClient(app) as client:
            created = client.post("/api/projects", json={"name": "Core", "description": ""})
            listed = client.get("/api/projects")
    finally:
        app.dependency_overrides.clear()
    assert created.status_code == 201
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == "project-1"


def test_user_create_contract_remains_available(monkeypatch) -> None:
    actor = User(id="admin", username="admin", password_hash="x", system_role="admin")
    created = User(id="user-1", username="member", password_hash="not-returned", name="Member", email="", system_role="user")

    async def override_user():
        return actor

    async def override_db():
        yield object()

    async def create_user(_db, _actor, _data):
        return created

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(identity, "create_user", create_user)
    try:
        response = TestClient(app).post("/api/auth/users", json={"username": "member", "password": "strong-password", "name": "Member"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert response.json()["data"]["username"] == "member"
    assert "password_hash" not in response.text
