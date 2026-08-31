import os

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-characters")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ai_test:change-me@localhost:5432/ai_test")

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_envelope() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert response.headers["X-Trace-Id"] == body["trace_id"]
