from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.errors import AppError
from app.models import ModelConfig, User
from app.schemas.model_settings import ModelConfigCreate, ModelConfigUpdate
from app.services import llm_probe, model_configs


class FakeDb:
    def __init__(self, row: ModelConfig | None = None):
        self.row = row
        self.added: list[ModelConfig] = []
        self.commits = 0
        self.executed = []

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None

    async def refresh(self, row):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None

    async def scalar(self, _statement):
        return self.row

    async def execute(self, statement, *args):
        self.executed.append((statement, args))
        return None


def admin() -> User:
    return User(id="admin-1", username="admin", password_hash="x", system_role="admin")


def payload(**overrides):
    values = {
        "name": "OpenAI",
        "provider": "openai",
        "protocol": "openai_chat",
        "model_name": "gpt-test",
        "api_key": "sk-" + "x" * 36 + "ab3f",
    }
    values.update(overrides)
    return ModelConfigCreate(**values)


@pytest.mark.asyncio
async def test_create_never_returns_or_persists_plaintext_api_key() -> None:
    db = FakeDb()
    secret = payload().api_key.get_secret_value()
    row = await model_configs.create(db, admin(), payload())
    output = model_configs.view(row)
    assert db.added == [row]
    assert row.api_key_encrypted != secret
    assert secret not in row.api_key_encrypted
    assert "api_key" not in output
    assert output["api_key_configured"] is True
    assert output["api_key_hint"] == "sk-***ab3f"


@pytest.mark.asyncio
async def test_empty_api_key_update_preserves_existing_encrypted_value() -> None:
    row = ModelConfig(id="model-1", name="OpenAI", provider="openai", protocol="openai_chat", model_name="gpt-test", api_key_encrypted="encrypted-old", api_key_hint="sk-***ab3f", extra_params={}, created_by="admin-1", revision=3)
    db = FakeDb(row)
    updated = await model_configs.update_config(db, admin(), row.id, ModelConfigUpdate(revision=3, model_name="gpt-next", api_key=""))
    assert updated.api_key_encrypted == "encrypted-old"
    assert updated.api_key_hint == "sk-***ab3f"
    assert updated.revision == 4


@pytest.mark.asyncio
async def test_set_default_clears_other_defaults_in_one_commit(monkeypatch) -> None:
    first = ModelConfig(id="model-1", name="First", provider="custom", protocol="openai_chat", model_name="first", api_key_encrypted="", api_key_hint="", extra_params={}, created_by="admin-1", is_default=True, revision=1)
    second = ModelConfig(id="model-2", name="Second", provider="custom", protocol="openai_chat", model_name="second", api_key_encrypted="", api_key_hint="", extra_params={}, created_by="admin-1", revision=2)
    db = FakeDb(second)

    async def make_default(_db, row):
        first.is_default = False
        second.is_default = False
        row.is_default = True

    monkeypatch.setattr(model_configs, "_make_default", make_default)
    await model_configs.set_default(db, admin(), second.id, 2)
    assert [row.is_default for row in (first, second)] == [False, True]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_non_admin_is_forbidden_before_database_access() -> None:
    db = FakeDb()
    user = User(id="user-1", username="member", password_hash="x", system_role="user")
    with pytest.raises(AppError) as caught:
        await model_configs.create(db, user, payload())
    assert caught.value.code == "AUTH_FORBIDDEN"
    assert db.added == []


@pytest.mark.asyncio
async def test_service_rejects_protocols_outside_the_server_whitelist() -> None:
    with pytest.raises(AppError) as caught:
        await model_configs.create(FakeDb(), admin(), payload(protocol="azure_openai"))
    assert caught.value.code == "MODEL_PROTOCOL_UNSUPPORTED"


@pytest.mark.asyncio
async def test_revision_conflict_has_no_sensitive_details() -> None:
    row = ModelConfig(id="model-1", name="OpenAI", provider="openai", protocol="openai_chat", model_name="gpt-test", api_key_encrypted="encrypted", api_key_hint="sk-***ab3f", extra_params={}, created_by="admin-1", revision=4)
    with pytest.raises(AppError) as caught:
        await model_configs.update_config(FakeDb(row), admin(), row.id, ModelConfigUpdate(revision=3, api_key="sk-" + "y" * 40))
    assert caught.value.code == "REVISION_CONFLICT"
    assert caught.value.details == {"current_revision": 4}


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "expected"), [(401, "AUTH_FAILED"), (404, "NOT_FOUND"), (429, "RATE_LIMITED"), (503, "UPSTREAM_ERROR")])
async def test_probe_classifies_mocked_upstream_responses_without_body_exposure(status: int, expected: str) -> None:
    config = SimpleNamespace(protocol="openai_chat", base_url="https://models.example.test/v1", model_name="test-model", timeout_seconds=2, extra_params={})
    transport = httpx.MockTransport(lambda _request: httpx.Response(status, text="upstream body is intentionally not returned"))
    result = await llm_probe.probe_config(config, "sk-" + "x" * 40, transport=transport)
    assert result["error_class"] == expected
    assert "upstream body" not in str(result)
    assert "sk-" not in str(result)


@pytest.mark.asyncio
async def test_probe_uses_an_explicit_timeout_for_network_errors() -> None:
    config = SimpleNamespace(protocol="gemini", base_url="https://models.example.test/v1", model_name="test-model", timeout_seconds=2, extra_params={})

    async def failing_handler(_request):
        raise httpx.ConnectError("not exposed")

    result = await llm_probe.probe_config(config, "", transport=httpx.MockTransport(failing_handler))
    assert result["error_class"] == "NETWORK"
