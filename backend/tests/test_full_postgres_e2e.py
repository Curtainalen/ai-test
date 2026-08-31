import os
import socket
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest

if os.getenv("RUN_POSTGRES_E2E") != "1":
    pytest.skip("set RUN_POSTGRES_E2E=1 with PostgreSQL and Redis", allow_module_level=True)

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from redis import Redis
from rq import Queue, SimpleWorker

from app.config import get_settings
from app.main import app

mock_app = FastAPI()
RUNTIME_TOKEN = "postgres-e2e-secret-token"


@mock_app.post("/login")
async def mock_login(payload: dict):
    if payload != {"username": "tester", "password": "test-password"}:
        raise HTTPException(401)
    return {"data": {"access_token": RUNTIME_TOKEN}}


@mock_app.get("/me")
async def mock_me(authorization: str = Header(default="")):
    if authorization != f"Bearer {RUNTIME_TOKEN}":
        raise HTTPException(401)
    return {"data": {"username": "tester", "email": "tester@example.test"}}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_worker() -> None:
    connection = Redis.from_url(get_settings().redis_url)
    SimpleWorker([Queue("default", connection=connection)], connection=connection).work(burst=True)


def test_full_requirement_api_execution_report_flow() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    redis.flushdb()
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started

    username = f"e2e_{int(time.time() * 1000)}"
    with TestClient(app) as client:
        response = client.post("/api/auth/register", json={"username": username, "password": "strong-e2e-password", "name": "E2E"})
        if response.status_code == 403:
            pytest.skip("database already contains a first user; use a clean E2E database")
        assert response.status_code == 201, response.text
        headers = {"Authorization": f"Bearer {response.json()['data']['access_token']}"}

        project = client.post("/api/projects", headers=headers, json={"name": "E2E Project", "description": ""}).json()["data"]
        environment = client.post(f"/api/projects/{project['id']}/environments", headers=headers, json={"name": "mock", "base_url": f"http://127.0.0.1:{port}", "variables": {}, "global_headers": {}, "secret_refs": {}, "is_enabled": True}).json()["data"]

        upload = client.post(f"/api/projects/{project['id']}/requirements/upload", headers=headers, files={"file": ("requirement.md", b"# User Login\nLogin and read current user.", "text/markdown")})
        assert upload.status_code == 202, upload.text
        run_worker()
        document_id = upload.json()["data"]["document_id"]
        document = client.get(f"/api/projects/{project['id']}/requirements/{document_id}", headers=headers).json()["data"]
        assert document["versions"][0]["parse_status"] == "completed"
        module = document["modules"][0]
        module = client.post(f"/api/projects/{project['id']}/requirement-modules/{module['id']}/confirm", headers=headers).json()["data"]
        assert module["status"] == "confirmed"

        spec = b'{"openapi":"3.1.0","paths":{"/login":{"post":{"tags":["Auth"],"responses":{"200":{"description":"ok"}}}},"/me":{"get":{"tags":["Auth"],"responses":{"200":{"description":"ok"}}}}}}'
        with patch(
            "app.api.assets.fetch_remote_openapi",
            new=AsyncMock(return_value=(spec, "https://docs.example.test/openapi.json")),
        ):
            remote_import = client.post(
                f"/api/projects/{project['id']}/api-imports/url",
                headers=headers,
                json={"url": "https://docs.example.test/openapi.json", "auth": {"type": "none"}},
            )
        assert remote_import.status_code == 201, remote_import.text
        assert remote_import.json()["data"]["source_type"] == "url"

        imported = client.post(f"/api/projects/{project['id']}/api-imports", headers=headers, files={"file": ("e2e.json", spec, "application/json")}).json()["data"]
        assert client.post(f"/api/projects/{project['id']}/api-imports/{imported['id']}/confirm", headers=headers, params={"revision": imported["revision"]}).status_code == 200
        interfaces = client.get(f"/api/projects/{project['id']}/interfaces", headers=headers).json()["data"]
        login = next(item for item in interfaces if item["path"] == "/login")
        me = next(item for item in interfaces if item["path"] == "/me")

        scenario_body = {"name": "Login flow", "description": "", "scenario_type": "api", "priority": "P0", "requirement_module_ids": [module["id"]], "steps": [
            {"seq": 1, "name": "Login", "interface_id": login["id"], "request_override": {"body_type": "json", "body": {"username": "tester", "password": "test-password"}}, "preconditions": [], "extracts": [{"name": "access_token", "type": "jmespath", "expression": "data.access_token", "scope": "scenario", "sensitive": True}], "assertions": [{"type": "status_code", "expected": 200}], "expected_result": "ok", "timeout_ms": 10000, "retry_count": 0, "continue_on_failure": False},
            {"seq": 2, "name": "Me", "interface_id": me["id"], "request_override": {"headers": {"Authorization": "Bearer ${access_token}"}}, "preconditions": [], "extracts": [], "assertions": [{"type": "status_code", "expected": 200}, {"type": "json_field", "field": "data.username", "expected": "tester"}], "expected_result": "ok", "timeout_ms": 10000, "retry_count": 0, "continue_on_failure": False},
        ]}
        scenario = client.post(f"/api/projects/{project['id']}/scenarios", headers=headers, json=scenario_body).json()["data"]
        assert client.post(f"/api/projects/{project['id']}/executions", headers={**headers, "Idempotency-Key": "before-confirm"}, json={"scenario_id": scenario["id"], "environment_id": environment["id"]}).status_code == 409
        scenario = client.post(f"/api/projects/{project['id']}/scenarios/{scenario['id']}/confirm", headers=headers, params={"revision": scenario["revision"]}).json()["data"]
        execution = client.post(f"/api/projects/{project['id']}/executions", headers={**headers, "Idempotency-Key": "e2e-execution"}, json={"scenario_id": scenario["id"], "environment_id": environment["id"]}).json()["data"]
        duplicate = client.post(f"/api/projects/{project['id']}/executions", headers={**headers, "Idempotency-Key": "e2e-execution"}, json={"scenario_id": scenario["id"], "environment_id": environment["id"]}).json()["data"]
        assert duplicate["id"] == execution["id"]
        run_worker()
        detail = client.get(f"/api/projects/{project['id']}/executions/{execution['id']}", headers=headers).json()["data"]
        assert detail["status"] == "completed", detail
        reports = client.get(f"/api/projects/{project['id']}/reports", headers=headers, params={"scenario_id": scenario["id"]}).json()["data"]
        report = client.get(f"/api/projects/{project['id']}/reports/{reports[0]['id']}", headers=headers).json()["data"]
        assert report["status"] == "passed"
        assert RUNTIME_TOKEN not in str(report)
        assert report["steps"][0]["request"]["body"]["password"] == "******"
        coverage = client.get(f"/api/projects/{project['id']}/requirement-coverage", headers=headers).json()["data"]
        assert next(item for item in coverage if item["requirement_module_id"] == module["id"])["status"] == "passed"

    server.should_exit = True
    thread.join(timeout=5)
