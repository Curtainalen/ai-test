import asyncio
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models import User
from app.services import reporting


class ScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class ReportDb:
    def __init__(self, api_reports, ui_reports):
        self.api_reports = api_reports
        self.ui_reports = ui_reports

    async def scalars(self, statement):
        sql = str(statement)
        if "FROM test_reports" in sql:
            return ScalarRows(self.api_reports)
        if "FROM ui_execution_reports" in sql:
            return ScalarRows(self.ui_reports)
        raise AssertionError(f"unexpected statement: {sql}")


def api_report(report_id: str, *, status: str, created_at: datetime, environment_id: str = "env-1"):
    return SimpleNamespace(
        id=report_id, execution_id=f"execution-{report_id}", status=status,
        summary={"total": 2}, scenario_snapshot={"id": "api-scenario", "name": "API 登录"},
        environment_snapshot={"id": environment_id, "name": "测试"}, requirement_snapshot=[],
        triggered_by_snapshot={"id": "user-1"}, started_at=created_at, finished_at=created_at,
        created_at=created_at,
    )


def ui_report(report_id: str, *, status: str, created_at: datetime, environment_id: str = "env-1"):
    return SimpleNamespace(
        id=report_id, execution_id=f"execution-{report_id}", status=status,
        summary={"total": 3}, scenario_snapshot={"id": "ui-scenario", "name": "UI 登录"},
        environment_snapshot={"id": environment_id, "name": "测试"}, trace_manifest_ref="trace-1",
        started_at=created_at, finished_at=created_at, created_at=created_at,
    )


def test_summary_uses_one_status_contract_for_api_and_ui_reports():
    reports = [
        reporting.api_report_view(api_report("api-1", status="passed", created_at=datetime(2026, 9, 1, tzinfo=UTC))),
        reporting.ui_report_view(ui_report("ui-1", status="completed", created_at=datetime(2026, 9, 1, tzinfo=UTC))),
        reporting.ui_report_view(ui_report("ui-2", status="failed", created_at=datetime(2026, 9, 2, tzinfo=UTC))),
    ]

    summary = reporting.summary_view(reports, Counter({"LOCATOR_BROKEN": 2, "HTTP_ERROR": 1}))

    assert summary["overview"] == {"total": 3, "passed": 2, "failed": 1, "canceled": 0, "other": 0, "pass_rate": 66.67}
    assert summary["by_type"]["api"]["total"] == 1
    assert summary["by_type"]["ui"]["passed"] == 1
    assert summary["trend"] == [
        {"date": "2026-09-01", "total": 2, "passed": 2, "failed": 0, "canceled": 0, "other": 0, "pass_rate": 100.0},
        {"date": "2026-09-02", "total": 1, "passed": 0, "failed": 1, "canceled": 0, "other": 0, "pass_rate": 0.0},
    ]
    assert summary["failure_categories"] == [
        {"category": "LOCATOR_BROKEN", "count": 2}, {"category": "HTTP_ERROR", "count": 1},
    ]


def test_list_reports_merges_sorts_and_filters_api_and_ui_facts(monkeypatch):
    async def allow(*_args, **_kwargs):
        return None

    monkeypatch.setattr(reporting, "require_membership", allow)
    db = ReportDb(
        [api_report("api-1", status="passed", created_at=datetime(2026, 9, 1, tzinfo=UTC))],
        [
            ui_report("ui-1", status="failed", created_at=datetime(2026, 9, 3, tzinfo=UTC)),
            ui_report("ui-2", status="completed", created_at=datetime(2026, 9, 2, tzinfo=UTC), environment_id="env-2"),
        ],
    )

    page = asyncio.run(reporting.list_reports(
        db, "project-1", SimpleNamespace(), page=1, page_size=20, environment_id="env-1",
    ))

    assert page["total"] == 2
    assert [(item["report_type"], item["id"], item["status"]) for item in page["items"]] == [
        ("ui", "ui-1", "failed"), ("api", "api-1", "passed"),
    ]
    assert all("_sort_at" not in item for item in page["items"])


def test_reporting_routes_expose_the_project_scoped_query_contract(monkeypatch):
    async def override_user():
        return User(id="user-1", username="member", password_hash="x")

    async def override_db():
        yield object()

    async def fake_list(*_args, **kwargs):
        assert kwargs["report_type"] == "ui"
        assert kwargs["status"] == "failed"
        return {"items": [{"id": "report-1", "report_type": "ui"}], "page": 1, "page_size": 20, "total": 1}

    async def fake_summary(*_args, **_kwargs):
        return {"overview": {"total": 1}}

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(reporting, "list_reports", fake_list)
    monkeypatch.setattr(reporting, "summary", fake_summary)
    try:
        with TestClient(app) as client:
            reports = client.get("/api/projects/project-1/reporting/reports?report_type=ui&status=failed")
            summary = client.get("/api/projects/project-1/reporting/summary")
    finally:
        app.dependency_overrides.clear()

    assert reports.status_code == 200
    assert reports.json()["data"]["items"][0]["report_type"] == "ui"
    assert summary.status_code == 200
    assert summary.json()["data"]["overview"]["total"] == 1
