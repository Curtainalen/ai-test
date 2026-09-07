"""Read-only, project-scoped reporting over API and UI report facts."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import ReportStep, TestReport, UiExecutionReport, UiExecutionReportStep, User
from app.services.identity import require_membership

ReportType = Literal["api", "ui"]


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _canonical_status(value: str) -> str:
    status = (value or "").lower()
    if status in {"passed", "completed"}:
        return "passed"
    if status in {"failed", "error"}:
        return "failed"
    if status == "canceled":
        return "canceled"
    return status or "unknown"


def api_report_view(row: TestReport) -> dict:
    return {
        "id": row.id,
        "report_type": "api",
        "execution_id": row.execution_id,
        "status": _canonical_status(row.status),
        "summary": row.summary or {},
        "scenario": row.scenario_snapshot or {},
        "environment": row.environment_snapshot or {},
        "requirements": row.requirement_snapshot or [],
        "triggered_by": row.triggered_by_snapshot or {},
        "trace_manifest_ref": None,
        "started_at": _time(row.started_at),
        "finished_at": _time(row.finished_at),
        "created_at": _time(row.created_at),
        "_sort_at": row.created_at or row.finished_at or row.started_at,
    }


def ui_report_view(row: UiExecutionReport) -> dict:
    return {
        "id": row.id,
        "report_type": "ui",
        "execution_id": row.execution_id,
        "status": _canonical_status(row.status),
        "summary": row.summary or {},
        "scenario": row.scenario_snapshot or {},
        "environment": row.environment_snapshot or {},
        "requirements": [],
        "triggered_by": {},
        "trace_manifest_ref": row.trace_manifest_ref,
        "started_at": _time(row.started_at),
        "finished_at": _time(row.finished_at),
        "created_at": _time(row.created_at),
        "_sort_at": row.created_at or row.finished_at or row.started_at,
    }


def _public_view(report: dict) -> dict:
    return {key: value for key, value in report.items() if not key.startswith("_")}


def _matches(report: dict, *, report_type: ReportType | None, status: str | None,
             environment_id: str | None, scenario_id: str | None) -> bool:
    return (
        (report_type is None or report["report_type"] == report_type)
        and (status is None or report["status"] == _canonical_status(status))
        and (environment_id is None or report["environment"].get("id") == environment_id)
        and (scenario_id is None or report["scenario"].get("id") == scenario_id)
    )


async def _reports(db: AsyncSession, project_id: str, *, report_type: ReportType | None = None,
                   status: str | None = None, environment_id: str | None = None,
                   scenario_id: str | None = None, started_from: datetime | None = None,
                   started_to: datetime | None = None) -> list[dict]:
    reports: list[dict] = []
    if report_type in {None, "api"}:
        stmt = select(TestReport).where(TestReport.project_id == project_id)
        if started_from is not None:
            stmt = stmt.where(TestReport.started_at >= started_from)
        if started_to is not None:
            stmt = stmt.where(TestReport.started_at <= started_to)
        reports.extend(api_report_view(row) for row in (await db.scalars(stmt)).all())
    if report_type in {None, "ui"}:
        stmt = select(UiExecutionReport).where(UiExecutionReport.project_id == project_id)
        if started_from is not None:
            stmt = stmt.where(UiExecutionReport.started_at >= started_from)
        if started_to is not None:
            stmt = stmt.where(UiExecutionReport.started_at <= started_to)
        reports.extend(ui_report_view(row) for row in (await db.scalars(stmt)).all())
    reports = [report for report in reports if _matches(
        report, report_type=report_type, status=status, environment_id=environment_id, scenario_id=scenario_id,
    )]
    return sorted(reports, key=lambda item: item["_sort_at"] or datetime.min.replace(tzinfo=UTC), reverse=True)


def _counts(reports: list[dict]) -> dict:
    statuses = Counter(report["status"] for report in reports)
    passed = statuses["passed"]
    failed = statuses["failed"]
    terminal = passed + failed
    return {
        "total": len(reports),
        "passed": passed,
        "failed": failed,
        "canceled": statuses["canceled"],
        "other": len(reports) - passed - failed - statuses["canceled"],
        "pass_rate": round(passed / terminal * 100, 2) if terminal else None,
    }


def summary_view(reports: list[dict], failure_categories: Counter[str]) -> dict:
    by_type = {
        report_type: _counts([report for report in reports if report["report_type"] == report_type])
        for report_type in ("api", "ui")
    }
    trends: dict[str, list[dict]] = defaultdict(list)
    for report in reports:
        occurred_at = report.get("finished_at") or report.get("created_at") or report.get("started_at")
        if occurred_at:
            trends[datetime.fromisoformat(occurred_at).date().isoformat()].append(report)
    return {
        "overview": _counts(reports),
        "by_type": by_type,
        "trend": [{"date": date, **_counts(items)} for date, items in sorted(trends.items())],
        "failure_categories": [
            {"category": category, "count": count}
            for category, count in failure_categories.most_common()
        ],
    }


async def _failure_categories(db: AsyncSession, project_id: str, reports: list[dict]) -> Counter[str]:
    api_ids = [report["id"] for report in reports if report["report_type"] == "api"]
    ui_ids = [report["id"] for report in reports if report["report_type"] == "ui"]
    categories: Counter[str] = Counter()
    if api_ids:
        values = (await db.scalars(select(ReportStep.error_category).where(
            ReportStep.project_id == project_id, ReportStep.report_id.in_(api_ids),
            ReportStep.error_category.is_not(None),
        ))).all()
        categories.update(values)
    if ui_ids:
        values = (await db.scalars(select(UiExecutionReportStep.error_category).where(
            UiExecutionReportStep.project_id == project_id, UiExecutionReportStep.report_id.in_(ui_ids),
            UiExecutionReportStep.error_category.is_not(None),
        ))).all()
        categories.update(values)
    return categories


async def list_reports(db: AsyncSession, project_id: str, user: User, *, page: int, page_size: int,
                       report_type: ReportType | None = None, status: str | None = None,
                       environment_id: str | None = None, scenario_id: str | None = None,
                       started_from: datetime | None = None, started_to: datetime | None = None) -> dict:
    await require_membership(db, project_id, user)
    reports = await _reports(db, project_id, report_type=report_type, status=status,
                             environment_id=environment_id, scenario_id=scenario_id,
                             started_from=started_from, started_to=started_to)
    offset = (page - 1) * page_size
    return {"items": [_public_view(report) for report in reports[offset:offset + page_size]],
            "page": page, "page_size": page_size, "total": len(reports)}


async def summary(db: AsyncSession, project_id: str, user: User, *, report_type: ReportType | None = None,
                  status: str | None = None, environment_id: str | None = None,
                  scenario_id: str | None = None, started_from: datetime | None = None,
                  started_to: datetime | None = None) -> dict:
    await require_membership(db, project_id, user)
    reports = await _reports(db, project_id, report_type=report_type, status=status,
                             environment_id=environment_id, scenario_id=scenario_id,
                             started_from=started_from, started_to=started_to)
    return summary_view(reports, await _failure_categories(db, project_id, reports))


async def report_detail(db: AsyncSession, project_id: str, user: User, report_type: ReportType, report_id: str) -> dict:
    await require_membership(db, project_id, user)
    if report_type == "api":
        report = await db.scalar(select(TestReport).where(TestReport.id == report_id, TestReport.project_id == project_id))
        if report is None:
            raise AppError("RESOURCE_NOT_FOUND", "报告不存在", 404)
        steps = list((await db.scalars(select(ReportStep).where(ReportStep.report_id == report.id).order_by(ReportStep.seq))).all())
        data = api_report_view(report)
        data["steps"] = [{"seq": step.seq, "name": step.name, "status": _canonical_status(step.status),
                          "duration_ms": step.duration_ms, "request": step.request_snapshot, "response": step.response_snapshot,
                          "extracted": step.extracted, "assertions": step.assertions, "error_category": step.error_category,
                          "error_message": step.error_message, "repro_steps": step.repro_steps} for step in steps]
    else:
        report = await db.scalar(select(UiExecutionReport).where(
            UiExecutionReport.id == report_id, UiExecutionReport.project_id == project_id,
        ))
        if report is None:
            raise AppError("RESOURCE_NOT_FOUND", "报告不存在", 404)
        steps = list((await db.scalars(select(UiExecutionReportStep).where(
            UiExecutionReportStep.report_id == report.id,
        ).order_by(UiExecutionReportStep.seq))).all())
        data = ui_report_view(report)
        data["steps"] = [{"seq": step.seq, "name": step.name, "status": _canonical_status(step.status),
                          "duration_ms": step.duration_ms, "action": step.action_snapshot, "result": step.result_snapshot,
                          "evidence_refs": step.evidence_refs, "error_category": step.error_category,
                          "error_message": step.error_message} for step in steps]
    return _public_view(data)
