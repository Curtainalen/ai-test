import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.api import evidence
from app.errors import AppError
from app.services import requirement_reviews, ui_runtime


class FakeDb:
    def __init__(self, scalars=None):
        self.values = list(scalars or [])
        self.statements = []
        self.committed = False

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.values.pop(0) if self.values else None

    async def commit(self):
        self.committed = True


def no_membership_check(*_args):
    return asyncio.sleep(0)


def test_candidate_review_transition_and_unapproved_materialization(monkeypatch):
    candidate = SimpleNamespace(
        id="candidate-1", project_id="project-1", candidate_type="automation_bundle", status="pending_review",
        exploration_id="exploration-1", execution_id=None, content={}, source_evidence_ids=[], rejection_reason=None,
        confirmed_asset_id=None, reviewed_by=None, reviewed_at=None, created_at=None,
    )
    db = FakeDb()
    monkeypatch.setattr(ui_runtime, "require_membership", no_membership_check)

    async def one(*_args):
        return candidate

    monkeypatch.setattr(ui_runtime, "_one", one)
    result = asyncio.run(ui_runtime.review_candidate(db, "project-1", SimpleNamespace(id="reviewer"), "candidate-1", SimpleNamespace(decision="rejected", reason="范围不正确")))
    assert result["status"] == "rejected" and candidate.reviewed_by == "reviewer" and db.committed

    candidate.status = "pending_review"
    with pytest.raises(AppError) as caught:
        asyncio.run(ui_runtime.confirm_candidate_bundle(db, "project-1", SimpleNamespace(id="reviewer"), "candidate-1"))
    assert caught.value.code == "UI_CANDIDATE_NOT_CONFIRMABLE"


def test_cross_project_or_unapproved_coverage_reference_is_rejected(monkeypatch):
    db = FakeDb([None, SimpleNamespace(id="scenario-1")])
    monkeypatch.setattr(requirement_reviews, "require_membership", no_membership_check)
    data = SimpleNamespace(test_point_id="other-project-point", scenario_type="ui", scenario_id="scenario-1")
    with pytest.raises(AppError) as caught:
        asyncio.run(requirement_reviews.create_coverage(db, "project-1", SimpleNamespace(id="user-1"), data))
    assert caught.value.code == "REQUIREMENT_COVERAGE_REFERENCE_INVALID"
    assert "requirement_test_points.project_id" in str(db.statements[0])


def test_evidence_path_escape_and_cross_project_query_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence, "require_membership", no_membership_check)
    monkeypatch.setattr(evidence, "get_settings", lambda: SimpleNamespace(upload_root=tmp_path / "uploads"))
    row = SimpleNamespace(id="evidence-1", object_key="../outside.txt", content_type="text/plain", kind="log")
    db = FakeDb([row])
    with pytest.raises(AppError) as caught:
        asyncio.run(evidence.get_evidence("project-1", "evidence-1", db, SimpleNamespace(id="user-1")))
    assert caught.value.code == "UI_EVIDENCE_UNAVAILABLE"
    query = str(db.statements[0])
    assert "ui_evidence.project_id" in query and "ui_evidence.id" in query
