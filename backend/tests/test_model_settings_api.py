from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models import User


class UnusedDb:
    async def scalars(self, _statement):
        raise AssertionError("non-admin requests must be rejected before database access")


class CreateDb:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None

    async def refresh(self, _row):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


def test_model_settings_route_rejects_non_admin_without_returning_request_content() -> None:
    user = User(id="user-1", username="member", password_hash="x", system_role="user")

    async def override_user():
        return user

    async def override_db():
        yield UnusedDb()

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/settings/model-configs")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_FORBIDDEN"


def test_create_response_never_contains_submitted_api_key() -> None:
    user = User(id="admin-1", username="admin", password_hash="x", system_role="admin")
    db = CreateDb()
    secret = "sk-" + "z" * 40

    async def override_user():
        return user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post("/api/settings/model-configs", json={"name": "HTTP test", "provider": "custom", "protocol": "openai_chat", "model_name": "test-model", "api_key": secret})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    assert secret not in response.text
    assert secret not in db.added[0].api_key_encrypted
    assert response.json()["data"]["api_key_configured"] is True
