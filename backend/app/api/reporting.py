from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.services import reporting

router = APIRouter(prefix="/projects/{project_id}/reporting", tags=["reporting"])


@router.get("/summary")
async def get_summary(
    project_id: str, request: Request, db: DbSession, user: CurrentUser,
    report_type: Literal["api", "ui"] | None = None, status: str | None = None,
    environment_id: str | None = None, scenario_id: str | None = None,
    started_from: datetime | None = None, started_to: datetime | None = None,
):
    return success(await reporting.summary(
        db, project_id, user, report_type=report_type, status=status, environment_id=environment_id,
        scenario_id=scenario_id, started_from=started_from, started_to=started_to,
    ), request.state.trace_id)


@router.get("/reports")
async def get_reports(
    project_id: str, request: Request, db: DbSession, user: CurrentUser,
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    report_type: Literal["api", "ui"] | None = None, status: str | None = None,
    environment_id: str | None = None, scenario_id: str | None = None,
    started_from: datetime | None = None, started_to: datetime | None = None,
):
    return success(await reporting.list_reports(
        db, project_id, user, page=page, page_size=page_size, report_type=report_type, status=status,
        environment_id=environment_id, scenario_id=scenario_id, started_from=started_from, started_to=started_to,
    ), request.state.trace_id)


@router.get("/reports/{report_type}/{report_id}")
async def get_report_detail(project_id: str, report_type: Literal["api", "ui"], report_id: str,
                            request: Request, db: DbSession, user: CurrentUser):
    return success(await reporting.report_detail(db, project_id, user, report_type, report_id), request.state.trace_id)
