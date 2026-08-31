import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, task):
        self.task = task

    async def get(self, model, key):
        return SimpleNamespace(id=key, is_active=True)

    async def scalar(self, query):
        return self.task

    async def scalars(self, query):
        return ScalarRows([])


class FakeSessionContext:
    def __init__(self, task):
        self.session = FakeSession(task)

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePubSub:
    def __init__(self):
        self.sent = False

    async def subscribe(self, channel):
        return None

    async def get_message(self, **kwargs):
        if self.sent:
            return None
        self.sent = True
        return {"data": json.dumps({"type": "execution_update", "version": 4, "data": {"status": "running"}})}

    async def unsubscribe(self, channel):
        return None

    async def close(self):
        return None


class FakeRedis:
    def pubsub(self):
        return FakePubSub()

    async def close(self):
        return None


def execution_task():
    return SimpleNamespace(
        id="execution-1",
        project_id="project-1",
        scenario_id="scenario-1",
        environment_id="environment-1",
        status="pending",
        cancel_requested=False,
        event_version=3,
        error_category=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    )


def test_websocket_sends_snapshot_events_and_recovers_snapshot_after_reconnect() -> None:
    task = execution_task()
    with (
        patch("app.ws.decode_access_token", return_value="user-1"),
        patch("app.ws.AsyncSessionLocal", side_effect=lambda: FakeSessionContext(task)),
        patch("app.ws.Redis.from_url", return_value=FakeRedis()),
        TestClient(app) as client,
    ):
        for attempt in range(2):
            with client.websocket_connect("/ws/projects/project-1/executions/execution-1") as socket:
                socket.send_json({"type": "auth", "token": "jwt"})
                snapshot = socket.receive_json()
                assert snapshot["type"] == "snapshot"
                assert snapshot["version"] == 3
                assert snapshot["data"]["status"] == "pending"
                if attempt == 0:
                    event = socket.receive_json()
                    assert event == {
                        "type": "execution_update",
                        "version": 4,
                        "data": {"status": "running"},
                    }
