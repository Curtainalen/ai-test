from fastapi import APIRouter, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.ui_collection import UiCollectionCreate, UiLocatorRevisionCreate, UiLocatorRevisionDecision
from app.services import ui_collection

router = APIRouter(prefix="/projects/{project_id}/ui/collections", tags=["ui-collection"])


@router.post("", status_code=202)
async def create_collection(project_id: str, data: UiCollectionCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_collection.create(db, project_id, user, data), request.state.trace_id)


@router.get("/{session_id}")
async def get_collection(project_id: str, session_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_collection.detail(db, project_id, user, session_id), request.state.trace_id)


@router.post("/locator-candidates/{candidate_id}/verify", status_code=202)
async def verify_candidate(project_id: str, candidate_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_collection.request_candidate_verification(db, project_id, user, candidate_id), request.state.trace_id)


@router.post("/locator-revisions", status_code=201)
async def create_locator_revision(project_id: str, data: UiLocatorRevisionCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_collection.propose_revision(db, project_id, user, data.candidate_id, data.ui_element_id), request.state.trace_id)


@router.post("/locator-revisions/{revision_id}/decision")
async def decide_locator_revision(project_id: str, revision_id: str, data: UiLocatorRevisionDecision,
                                  request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_collection.decide_revision(db, project_id, user, revision_id, data.decision), request.state.trace_id)
