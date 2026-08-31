import asyncio
from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.schemas.ai import ApiScenarioCandidateDecision
from app.services import api_candidates


class Scalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, scalar_values=None, scalar_rows=None):
        self.scalar_values = list(scalar_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.added = []
        self.statements = []

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, statement):
        self.statements.append(statement)
        return Scalars(self.scalar_rows.pop(0) if self.scalar_rows else [])

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        pass


def candidate(**overrides):
    values = {
        "id": "candidate-1", "project_id": "project-1", "model_config_id": "model-1",
        "model_config_revision_id": None, "llm_call_id": None,
        "interface_ids": ["interface-1"], "requirement_test_point_ids": ["point-1"],
        "instruction": "生成登录场景", "content": {}, "status": "pending_review",
        "revision": 2, "cancel_requested": False, "error_code": None, "error_message": None,
        "confirmed_asset_id": None, "reviewed_by": None, "reviewed_at": None, "created_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def allow_membership(*_args):
    return asyncio.sleep(0)


def test_cross_project_interface_is_rejected():
    db = FakeDb(scalar_rows=[[]])
    with pytest.raises(AppError) as caught:
        asyncio.run(api_candidates._validated_sources(db, "project-1", ["other-project-interface"], []))
    assert caught.value.code == "API_CANDIDATE_INTERFACE_INVALID"
    assert "api_interfaces.project_id" in str(db.statements[0])


def test_candidate_requires_review_and_revision_match(monkeypatch):
    monkeypatch.setattr(api_candidates, "require_membership", allow_membership)
    row = candidate(status="generating")
    db = FakeDb(scalar_values=[row])
    with pytest.raises(AppError) as caught:
        asyncio.run(api_candidates.materialize(db, "project-1", SimpleNamespace(id="user-1"), row.id, 2))
    assert caught.value.code == "API_CANDIDATE_NOT_CONFIRMABLE"

    row.status = "pending_review"
    db = FakeDb(scalar_values=[row])
    data = ApiScenarioCandidateDecision(decision="approved", revision=1)
    with pytest.raises(AppError) as caught:
        asyncio.run(api_candidates.decide(db, "project-1", SimpleNamespace(id="user-1"), row.id, data))
    assert caught.value.code == "REVISION_CONFLICT"


def test_approved_candidate_materializes_only_draft(monkeypatch):
    monkeypatch.setattr(api_candidates, "require_membership", allow_membership)
    row = candidate(
        status="approved",
        content={"proposal": {
            "name": "登录接口场景", "description": "", "priority": "P1",
            "requirement_test_point_ids": ["point-1"],
            "steps": [{"seq": 1, "name": "登录", "interface_id": "interface-1",
                       "expected_result": "返回成功", "assertions": [{"type": "status_code", "expected": 200}],
                       "test_data_refs": ["secret://login/user"], "timeout_ms": 30000}],
        }},
    )
    point = SimpleNamespace(id="point-1", review_id="review-1")
    review = SimpleNamespace(id="review-1", requirement_module_id="module-1")
    db = FakeDb(scalar_values=[row], scalar_rows=[[review]])

    async def sources(*_args):
        return [SimpleNamespace(id="interface-1")], [point]

    async def create_scenario(_db, _project_id, _user, data):
        assert data.steps[0].request_override == {"candidate_test_data_refs": ["secret://login/user"]}
        return {"id": "scenario-1", "status": "draft", "revision": 1}

    monkeypatch.setattr(api_candidates, "_validated_sources", sources)
    monkeypatch.setattr(api_candidates.scenarios, "create", create_scenario)
    result = asyncio.run(api_candidates.materialize(db, "project-1", SimpleNamespace(id="user-1"), row.id, 2))
    assert result["scenario"]["status"] == "draft"
    assert result["candidate"]["status"] == "superseded"
    assert db.added[0].status == "CANDIDATE"


def test_generating_candidate_can_be_canceled(monkeypatch):
    monkeypatch.setattr(api_candidates, "require_membership", allow_membership)
    row = candidate(status="generating")
    db = FakeDb(scalar_values=[row])
    result = asyncio.run(api_candidates.cancel(db, "project-1", SimpleNamespace(id="user-1"), row.id))
    assert result["status"] == "canceled"
    assert result["cancel_requested"] is True
    assert result["revision"] == 3
