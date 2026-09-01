from fastapi import APIRouter, Query, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.ai import (ApiScenarioCandidateCreate, ApiScenarioCandidateDecision,
                            ApiScenarioCandidateMaterialize, RequirementCoverageCreate,
                            RequirementReviewCreate, RequirementReviewDecision)
from app.services import api_candidates, requirement_reviews

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai-orchestration"])


@router.post("/requirement-reviews", status_code=202)
async def create_review(project_id: str, data: RequirementReviewCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await requirement_reviews.create(db, project_id, user, data), request.state.trace_id)


@router.get("/requirement-reviews")
async def list_reviews(project_id: str, request: Request, db: DbSession, user: CurrentUser,
                       page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return success(await requirement_reviews.list_reviews(db, project_id, user, page, page_size), request.state.trace_id)


@router.get("/requirement-reviews/{review_id}")
async def get_review(project_id: str, review_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await requirement_reviews.detail(db, project_id, user, review_id), request.state.trace_id)


@router.post("/requirement-reviews/{review_id}/decision")
async def decide_review(project_id: str, review_id: str, data: RequirementReviewDecision,
                        request: Request, db: DbSession, user: CurrentUser):
    return success(await requirement_reviews.decide(db, project_id, user, review_id, data.decision), request.state.trace_id)


@router.post("/requirement-reviews/{review_id}/cancel")
async def cancel_review(project_id: str, review_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await requirement_reviews.cancel(db, project_id, user, review_id), request.state.trace_id)


@router.post("/requirement-coverages", status_code=201)
async def create_coverage(project_id: str, data: RequirementCoverageCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await requirement_reviews.create_coverage(db, project_id, user, data), request.state.trace_id)


@router.get("/requirement-coverages")
async def list_coverages(project_id: str, request: Request, db: DbSession, user: CurrentUser,
                         page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return success(await requirement_reviews.list_coverages(db, project_id, user, page, page_size), request.state.trace_id)


@router.get("/requirement-test-points")
async def list_requirement_test_points(project_id: str, request: Request, db: DbSession, user: CurrentUser,
                                       page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=100)):
    return success(await requirement_reviews.list_approved_test_points(
        db, project_id, user, page, page_size), request.state.trace_id)


@router.post("/api-scenario-candidates", status_code=202)
async def create_api_candidate(project_id: str, data: ApiScenarioCandidateCreate, request: Request,
                               db: DbSession, user: CurrentUser):
    return success(await api_candidates.create(db, project_id, user, data), request.state.trace_id)


@router.get("/api-scenario-candidates")
async def list_api_candidates(project_id: str, request: Request, db: DbSession, user: CurrentUser,
                              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    return success(await api_candidates.list_candidates(db, project_id, user, page, page_size), request.state.trace_id)


@router.get("/api-scenario-candidates/{candidate_id}")
async def get_api_candidate(project_id: str, candidate_id: str, request: Request,
                            db: DbSession, user: CurrentUser):
    return success(await api_candidates.detail(db, project_id, user, candidate_id), request.state.trace_id)


@router.post("/api-scenario-candidates/{candidate_id}/decision")
async def decide_api_candidate(project_id: str, candidate_id: str, data: ApiScenarioCandidateDecision,
                               request: Request, db: DbSession, user: CurrentUser):
    return success(await api_candidates.decide(db, project_id, user, candidate_id, data), request.state.trace_id)


@router.post("/api-scenario-candidates/{candidate_id}/cancel")
async def cancel_api_candidate(project_id: str, candidate_id: str, request: Request,
                               db: DbSession, user: CurrentUser):
    return success(await api_candidates.cancel(db, project_id, user, candidate_id), request.state.trace_id)


@router.post("/api-scenario-candidates/{candidate_id}/materialize", status_code=201)
async def materialize_api_candidate(project_id: str, candidate_id: str, data: ApiScenarioCandidateMaterialize,
                                    request: Request, db: DbSession, user: CurrentUser):
    return success(await api_candidates.materialize(db, project_id, user, candidate_id, data.revision), request.state.trace_id)
