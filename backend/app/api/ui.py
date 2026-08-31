from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request

from app.dependencies import CurrentUser, DbSession
from app.response import success
from app.schemas.ui import (UiCandidateConfirmBundleRequest, UiCandidateGenerateRequest, UiCandidateReviewRequest, UiElementCreate, UiElementUpdate, UiExecutionCreate, UiExplorationActionRequest, UiExplorationCreate, UiListQuery, UiModuleCreate, UiModuleUpdate, UiPageCreate, UiPageLocatorVerifyRequest, UiPageStepCreate, UiPageStepDetailCreate, UiPageStepDetailUpdate, UiPageStepUpdate, UiPageUpdate, UiScenarioCreate, UiScenarioUpdate, UiVerifyRequest)
from app.schemas.ui import UiExplorationApprovalRequest
from app.services import ui_assets, ui_runtime, ui_verification

router = APIRouter(prefix="/projects/{project_id}/ui", tags=["ui-assets"])
ListQuery = Annotated[UiListQuery, Depends()]


@router.get("/modules")
async def list_modules(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.list_modules(db, project_id, user, query), request.state.trace_id)


@router.post("/modules", status_code=201)
async def create_module(project_id: str, data: UiModuleCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.create_module(db, project_id, user, data), request.state.trace_id)


@router.get("/modules/{module_id}")
async def get_module(project_id: str, module_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.get_module(db, project_id, user, module_id), request.state.trace_id)


@router.patch("/modules/{module_id}")
async def update_module(project_id: str, module_id: str, data: UiModuleUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.update_module(db, project_id, user, module_id, data), request.state.trace_id)


@router.delete("/modules/{module_id}", status_code=204)
async def delete_module(project_id: str, module_id: str, db: DbSession, user: CurrentUser):
    await ui_assets.delete_module(db, project_id, user, module_id)


@router.get("/pages")
async def list_pages(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser, module_id: str | None = None):
    return success(await ui_assets.list_pages(db, project_id, user, query, module_id), request.state.trace_id)


@router.post("/pages", status_code=201)
async def create_page(project_id: str, data: UiPageCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.create_page(db, project_id, user, data), request.state.trace_id)


@router.get("/pages/{page_id}")
async def get_page(project_id: str, page_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.get_page(db, project_id, user, page_id), request.state.trace_id)


@router.patch("/pages/{page_id}")
async def update_page(project_id: str, page_id: str, data: UiPageUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.update_page(db, project_id, user, page_id, data), request.state.trace_id)


@router.delete("/pages/{page_id}", status_code=204)
async def delete_page(project_id: str, page_id: str, db: DbSession, user: CurrentUser):
    await ui_assets.delete_page(db, project_id, user, page_id)


@router.post("/pages/{page_id}/verify-access", status_code=202)
async def verify_page_access(project_id: str, page_id: str, data: UiVerifyRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_verification.request_page_verification(db, project_id, user, page_id, data), request.state.trace_id)


@router.post("/pages/{page_id}/verify-locator", status_code=202)
async def verify_page_locator(project_id: str, page_id: str, data: UiPageLocatorVerifyRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_verification.request_locator_verification(db, project_id, user, page_id, data), request.state.trace_id)


@router.get("/elements")
async def list_elements(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser, page_id: str | None = None):
    return success(await ui_assets.list_elements(db, project_id, user, query, page_id), request.state.trace_id)


@router.post("/elements", status_code=201)
async def create_element(project_id: str, data: UiElementCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.create_element(db, project_id, user, data), request.state.trace_id)


@router.get("/elements/{element_id}")
async def get_element(project_id: str, element_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.get_element(db, project_id, user, element_id), request.state.trace_id)


@router.patch("/elements/{element_id}")
async def update_element(project_id: str, element_id: str, data: UiElementUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.update_element(db, project_id, user, element_id, data), request.state.trace_id)


@router.delete("/elements/{element_id}", status_code=204)
async def delete_element(project_id: str, element_id: str, db: DbSession, user: CurrentUser):
    await ui_assets.delete_element(db, project_id, user, element_id)


@router.post("/elements/{element_id}/verify", status_code=202)
async def verify_element(project_id: str, element_id: str, data: UiVerifyRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_verification.request_element_verification(db, project_id, user, element_id, data), request.state.trace_id)


@router.get("/page-steps")
async def list_page_steps(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser, page_id: str | None = None):
    return success(await ui_assets.list_page_steps(db, project_id, user, query, page_id), request.state.trace_id)


@router.post("/page-steps", status_code=201)
async def create_page_step(project_id: str, data: UiPageStepCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.create_page_step(db, project_id, user, data), request.state.trace_id)


@router.get("/page-steps/{step_id}")
async def get_page_step(project_id: str, step_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.get_page_step(db, project_id, user, step_id), request.state.trace_id)


@router.patch("/page-steps/{step_id}")
async def update_page_step(project_id: str, step_id: str, data: UiPageStepUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.update_page_step(db, project_id, user, step_id, data), request.state.trace_id)


@router.delete("/page-steps/{step_id}", status_code=204)
async def delete_page_step(project_id: str, step_id: str, db: DbSession, user: CurrentUser):
    await ui_assets.delete_page_step(db, project_id, user, step_id)


@router.post("/page-steps/{step_id}/details", status_code=201)
async def create_page_step_detail(project_id: str, step_id: str, data: UiPageStepDetailCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.create_page_step_detail(db, project_id, user, step_id, data), request.state.trace_id)


@router.patch("/page-steps/{step_id}/details/{detail_id}")
async def update_page_step_detail(project_id: str, step_id: str, detail_id: str, data: UiPageStepDetailUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.update_page_step_detail(db, project_id, user, step_id, detail_id, data), request.state.trace_id)


@router.delete("/page-steps/{step_id}/details/{detail_id}", status_code=204)
async def delete_page_step_detail(project_id: str, step_id: str, detail_id: str, db: DbSession, user: CurrentUser):
    await ui_assets.delete_page_step_detail(db, project_id, user, step_id, detail_id)


@router.get("/scenarios")
async def list_scenarios(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser, module_id: str | None = None):
    return success(await ui_assets.list_scenarios(db, project_id, user, query, module_id), request.state.trace_id)


@router.post("/scenarios", status_code=201)
async def create_scenario(project_id: str, data: UiScenarioCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.create_scenario(db, project_id, user, data), request.state.trace_id)


@router.get("/scenarios/{scenario_id}")
async def get_scenario(project_id: str, scenario_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.get_scenario(db, project_id, user, scenario_id), request.state.trace_id)


@router.patch("/scenarios/{scenario_id}")
async def update_scenario(project_id: str, scenario_id: str, data: UiScenarioUpdate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.update_scenario(db, project_id, user, scenario_id, data), request.state.trace_id)


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(project_id: str, scenario_id: str, db: DbSession, user: CurrentUser):
    await ui_assets.delete_scenario(db, project_id, user, scenario_id)


@router.post("/scenarios/{scenario_id}/confirm")
async def confirm_scenario(project_id: str, scenario_id: str, revision: int, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.confirm_scenario(db, project_id, user, scenario_id, revision), request.state.trace_id)


@router.get("/verifications")
async def list_verifications(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser, element_id: str | None = None, page_id: str | None = None):
    return success(await ui_assets.list_verifications(db, project_id, user, query, element_id, page_id), request.state.trace_id)


@router.get("/verifications/{verification_id}")
async def get_verification(project_id: str, verification_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_assets.get_verification(db, project_id, user, verification_id), request.state.trace_id)


@router.post("/verifications/{verification_id}/cancel")
async def cancel_verification(project_id: str, verification_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_verification.cancel_verification(db, project_id, user, verification_id), request.state.trace_id)


@router.get("/explorations")
async def list_explorations(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.list_explorations(db, project_id, user, query), request.state.trace_id)


@router.post("/explorations", status_code=201)
async def create_exploration(project_id: str, data: UiExplorationCreate, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.create_exploration(db, project_id, user, data), request.state.trace_id)


@router.get("/explorations/{exploration_id}")
async def get_exploration(project_id: str, exploration_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.exploration_detail(db, project_id, user, exploration_id), request.state.trace_id)


@router.post("/explorations/{exploration_id}/actions")
async def append_exploration_action(project_id: str, exploration_id: str, data: UiExplorationActionRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.append_exploration_action(db, project_id, user, exploration_id, data), request.state.trace_id)


@router.post("/explorations/{exploration_id}/start", status_code=202)
async def start_exploration(project_id: str, exploration_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.start_exploration(db, project_id, user, exploration_id), request.state.trace_id)


@router.post("/explorations/{exploration_id}/cancel")
async def cancel_exploration(project_id: str, exploration_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.cancel_exploration(db, project_id, user, exploration_id), request.state.trace_id)


@router.post("/explorations/{exploration_id}/turns/{turn_id}/decision")
async def decide_exploration_turn(project_id: str, exploration_id: str, turn_id: str, data: UiExplorationApprovalRequest,
                                  request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.decide_exploration_turn(db, project_id, user, exploration_id, turn_id, data.decision), request.state.trace_id)


@router.get("/executions")
async def list_ui_executions(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.list_executions(db, project_id, user, query), request.state.trace_id)


@router.post("/scenarios/{scenario_id}/executions", status_code=202)
async def create_ui_execution(project_id: str, scenario_id: str, data: UiExecutionCreate, request: Request, db: DbSession, user: CurrentUser, idempotency_key: str = Header(alias="Idempotency-Key")):
    row, created = await ui_runtime.create_execution(db, project_id, user, scenario_id, data, idempotency_key)
    return success({**row, "created": created}, request.state.trace_id)


@router.get("/executions/{execution_id}")
async def get_ui_execution(project_id: str, execution_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.execution_detail(db, project_id, user, execution_id), request.state.trace_id)


@router.post("/executions/{execution_id}/cancel")
async def cancel_ui_execution(project_id: str, execution_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.cancel_execution(db, project_id, user, execution_id), request.state.trace_id)


@router.get("/reports")
async def list_ui_reports(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.list_reports(db, project_id, user, query), request.state.trace_id)


@router.get("/reports/{report_id}")
async def get_ui_report(project_id: str, report_id: str, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.report_detail(db, project_id, user, report_id), request.state.trace_id)


@router.get("/candidates")
async def list_ui_candidates(project_id: str, query: ListQuery, request: Request, db: DbSession, user: CurrentUser, status: str | None = None):
    return success(await ui_runtime.list_candidates(db, project_id, user, query, status), request.state.trace_id)


@router.post("/candidates", status_code=202)
async def request_ui_candidate(project_id: str, data: UiCandidateGenerateRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.request_candidate(db, project_id, user, data), request.state.trace_id)


@router.post("/candidates/{candidate_id}/review")
async def review_ui_candidate(project_id: str, candidate_id: str, data: UiCandidateReviewRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.review_candidate(db, project_id, user, candidate_id, data), request.state.trace_id)


@router.post("/candidates/{candidate_id}/confirm-bundle", status_code=201)
async def confirm_ui_candidate_bundle(project_id: str, candidate_id: str, data: UiCandidateConfirmBundleRequest, request: Request, db: DbSession, user: CurrentUser):
    return success(await ui_runtime.confirm_candidate_bundle(db, project_id, user, candidate_id), request.state.trace_id)
