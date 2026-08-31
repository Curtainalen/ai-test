from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.config import get_settings
from app.dependencies import CurrentUser, DbSession
from app.errors import AppError
from app.models import UiEvidence
from app.services.identity import require_membership

router = APIRouter(prefix="/projects/{project_id}/ui/evidence", tags=["ui-evidence"])


@router.get("/{evidence_id}")
async def get_evidence(project_id: str, evidence_id: str, db: DbSession, user: CurrentUser):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(UiEvidence).where(UiEvidence.id == evidence_id, UiEvidence.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "证据不存在", 404)
    root = get_settings().upload_root.resolve()
    path = (root / row.object_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AppError("UI_EVIDENCE_UNAVAILABLE", "证据文件不可用", 404)
    return FileResponse(Path(path), media_type=row.content_type, filename=f"{row.kind}-{row.id}{path.suffix}")
