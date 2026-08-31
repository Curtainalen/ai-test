from __future__ import annotations

import asyncio
import json
import httpx
import pytest

from app.errors import AppError
from app.models import ModelConfig
from app.security import encrypt_secret
from app.services.llm.gateway import DefaultLlmGateway, _redact_text, _validate_schema


class FakeDb:
    def __init__(self, config):
        self.config = config
        self.scalar_calls = 0
        self.added = []

    async def scalar(self, _statement):
        self.scalar_calls += 1
        return self.config if self.scalar_calls == 1 else None

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        for index, row in enumerate(self.added, start=1):
            if not row.id:
                row.id = f"row-{index}"

    async def commit(self):
        await self.flush()

    async def rollback(self):
        return None


def config(api_key="top-secret-key"):
    return ModelConfig(id="config-1", name="test", provider="openai", protocol="openai_chat",
                       model_name="test-model", api_key_encrypted=encrypt_secret(api_key), api_key_hint="***",
                       extra_params={}, timeout_seconds=1, max_retries=0, is_enabled=True, revision=3,
                       created_by="user-1")


def test_redaction_and_structured_schema_validation():
    assert "top-secret" not in _redact_text("api_key=top-secret")
    _validate_schema({"items": [{"name": "ok"}]}, {"type": "object", "required": ["items"],
                     "properties": {"items": {"type": "array", "items": {"type": "object", "required": ["name"]}}}})
    with pytest.raises(AppError) as exc:
        _validate_schema({}, {"type": "object", "required": ["items"]})
    assert exc.value.code == "LLM_RESPONSE_SCHEMA_INVALID"


@pytest.mark.asyncio
async def test_gateway_records_revision_usage_and_never_persists_api_key():
    sent_request = None

    async def handler(request: httpx.Request):
        nonlocal sent_request
        sent_request = request
        assert request.headers["authorization"] == "Bearer top-secret-key"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer":"ok"}'}}]})

    db = FakeDb(config())
    result = await DefaultLlmGateway(db, transport=httpx.MockTransport(handler)).generate(
        project_id="project-1", model_config_id="config-1", prompt="password=hunter2 say hello",
        response_schema={"type": "object", "required": ["answer"], "properties": {"answer": {"type": "string"}}},
        timeout_ms=1000, created_by="user-1")
    assert result.data == {"answer": "ok"}
    assert result.usage_unknown is True
    record = db.added[-1]
    assert "hunter2" not in record.prompt_redacted
    assert "top-secret-key" not in record.prompt_redacted
    sent = json.loads(sent_request.content.decode())
    assert "hunter2" not in sent["messages"][0]["content"]
    assert "top-secret-key" not in sent["messages"][0]["content"]
    assert db.added[0].revision == 3


@pytest.mark.asyncio
async def test_gateway_timeout_has_stable_error_code():
    async def handler(_request: httpx.Request):
        raise httpx.ReadTimeout("slow")

    db = FakeDb(config(api_key=""))
    with pytest.raises(AppError) as exc:
        await DefaultLlmGateway(db, transport=httpx.MockTransport(handler)).generate(
            project_id="project-1", model_config_id="config-1", prompt="hello",
            response_schema={"type": "object"}, timeout_ms=100, created_by="user-1")
    assert exc.value.code == "LLM_TIMEOUT"
    assert db.added[-1].error_code == "LLM_TIMEOUT"


@pytest.mark.asyncio
async def test_gateway_cancels_an_inflight_request():
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_request: httpx.Request):
        started.set()
        await release.wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    cancellation = asyncio.Event()
    db = FakeDb(config())
    task = asyncio.create_task(DefaultLlmGateway(db, transport=httpx.MockTransport(handler)).generate(
        project_id="project-1", model_config_id="config-1", prompt="hello",
        response_schema={"type": "object"}, timeout_ms=5000, cancellation_token=cancellation,
        created_by="user-1"))
    await started.wait()
    cancellation.set()
    with pytest.raises(AppError) as exc:
        await task
    assert exc.value.code == "LLM_CALL_CANCELED"
    assert db.added[-1].status == "canceled"
