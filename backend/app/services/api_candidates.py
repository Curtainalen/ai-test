from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.errors import AppError
from app.models import (ApiInterface, ApiScenarioCandidate, ModelConfig, RequirementCoverage,
                        RequirementReview, RequirementTestPoint)
from app.schemas.ai import ApiScenarioProposal
from app.schemas.assets import ScenarioCreate
from app.services import scenarios
from app.services.identity import require_membership
from app.services.queue import enqueue_unique


def view(row: ApiScenarioCandidate) -> dict:
    return {
        "id": row.id, "project_id": row.project_id, "model_config_id": row.model_config_id,
        "model_config_revision_id": row.model_config_revision_id, "llm_call_id": row.llm_call_id,
        "interface_ids": row.interface_ids, "requirement_test_point_ids": row.requirement_test_point_ids,
        "instruction": row.instruction, "content": row.content, "status": row.status,
        "revision": row.revision, "cancel_requested": row.cancel_requested,
        "error_code": row.error_code, "error_message": row.error_message,
        "confirmed_asset_id": row.confirmed_asset_id, "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def _validated_sources(db, project_id: str, interface_ids: list[str], test_point_ids: list[str]):
    unique_interfaces = set(interface_ids)
    interfaces = list((await db.scalars(select(ApiInterface).where(
        ApiInterface.project_id == project_id, ApiInterface.id.in_(unique_interfaces),
        ApiInterface.is_deleted.is_(False)))).all())
    if len(interfaces) != len(unique_interfaces):
        raise AppError("API_CANDIDATE_INTERFACE_INVALID", "接口不存在、已删除或跨项目", 422)
    unique_points = set(test_point_ids)
    points = list((await db.scalars(select(RequirementTestPoint).join(
        RequirementReview, RequirementReview.id == RequirementTestPoint.review_id).where(
        RequirementTestPoint.project_id == project_id, RequirementTestPoint.id.in_(unique_points),
        RequirementReview.project_id == project_id, RequirementReview.status == "approved"))).all()) if unique_points else []
    if len(points) != len(unique_points):
        raise AppError("API_CANDIDATE_TEST_POINT_INVALID", "需求测试点未批准、不存在或跨项目", 422)
    return interfaces, points


async def create(db, project_id, user, data) -> dict:
    await require_membership(db, project_id, user)
    await _validated_sources(db, project_id, data.interface_ids, data.requirement_test_point_ids)
    config_stmt = select(ModelConfig).where(ModelConfig.is_enabled.is_(True))
    config_stmt = config_stmt.where(ModelConfig.id == data.model_config_id) if data.model_config_id else config_stmt.where(ModelConfig.is_default.is_(True))
    config = await db.scalar(config_stmt)
    if config is None or not config.api_key_encrypted:
        raise AppError("MODEL_CONFIG_NOT_FOUND", "模型配置不存在、未启用或未配置密钥", 404)
    row = ApiScenarioCandidate(project_id=project_id, model_config_id=config.id,
        interface_ids=list(dict.fromkeys(data.interface_ids)), requirement_test_point_ids=list(dict.fromkeys(data.requirement_test_point_ids)),
        instruction=data.instruction, status="generating", revision=1, created_by=user.id)
    db.add(row)
    await db.commit()
    try:
        enqueue_unique("app.ai_worker_jobs.generate_api_scenario_candidate_job", row.id, 180)
    except AppError as exc:
        row.status, row.error_code, row.error_message = "failed", exc.code, exc.message
        await db.commit()
        raise
    return view(row)


async def list_candidates(db, project_id, user, page: int, page_size: int) -> dict:
    await require_membership(db, project_id, user)
    stmt = select(ApiScenarioCandidate).where(ApiScenarioCandidate.project_id == project_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(ApiScenarioCandidate.created_at.desc()).offset(
        (page - 1) * page_size).limit(page_size))).all())
    return {"items": [view(row) for row in rows], "page": page, "page_size": page_size, "total": total}


async def detail(db, project_id, user, candidate_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await db.scalar(select(ApiScenarioCandidate).where(
        ApiScenarioCandidate.id == candidate_id, ApiScenarioCandidate.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "API 场景候选不存在", 404)
    return view(row)


async def decide(db, project_id, user, candidate_id: str, data) -> dict:
    await require_membership(db, project_id, user)
    row = await db.scalar(select(ApiScenarioCandidate).where(
        ApiScenarioCandidate.id == candidate_id, ApiScenarioCandidate.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "API 场景候选不存在", 404)
    if row.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "API 场景候选已被修改", 409, {"current_revision": row.revision})
    if row.status != "pending_review":
        raise AppError("API_CANDIDATE_NOT_REVIEWABLE", "API 场景候选不处于待审核状态", 409)
    row.status, row.reviewed_by, row.reviewed_at = data.decision, user.id, datetime.now(UTC)
    row.revision += 1
    if data.decision == "rejected":
        row.content = {**row.content, "rejection_reason": data.reason}
    await db.commit()
    return view(row)


async def cancel(db, project_id, user, candidate_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await db.scalar(select(ApiScenarioCandidate).where(
        ApiScenarioCandidate.id == candidate_id, ApiScenarioCandidate.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "API 场景候选不存在", 404)
    if row.status != "generating":
        raise AppError("API_CANDIDATE_NOT_CANCELABLE", "API 场景候选已进入终态", 409)
    row.cancel_requested, row.status, row.revision = True, "canceled", row.revision + 1
    await db.commit()
    return view(row)


async def materialize(db, project_id, user, candidate_id: str, revision: int) -> dict:
    await require_membership(db, project_id, user)
    row = await db.scalar(select(ApiScenarioCandidate).where(
        ApiScenarioCandidate.id == candidate_id, ApiScenarioCandidate.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "API 场景候选不存在", 404)
    if row.status == "superseded" and row.confirmed_asset_id:
        return {"candidate": view(row), "scenario": await scenarios.get(db, project_id, user, row.confirmed_asset_id), "created": False}
    if row.revision != revision:
        raise AppError("REVISION_CONFLICT", "API 场景候选已被修改", 409, {"current_revision": row.revision})
    if row.status != "approved":
        raise AppError("API_CANDIDATE_NOT_CONFIRMABLE", "API 场景候选必须先通过人工审核", 409)
    try:
        proposal = ApiScenarioProposal.model_validate((row.content or {}).get("proposal"))
    except ValueError as exc:
        raise AppError("API_CANDIDATE_CONTENT_INVALID", "API 场景候选结构无效", 409) from exc
    _interfaces, points = await _validated_sources(db, project_id,
        [step.interface_id for step in proposal.steps], proposal.requirement_test_point_ids)
    if any(step.interface_id not in row.interface_ids for step in proposal.steps) or any(
        point_id not in row.requirement_test_point_ids for point_id in proposal.requirement_test_point_ids):
        raise AppError("API_CANDIDATE_SOURCE_SCOPE_INVALID", "候选引用超出创建时批准的接口或测试点范围", 422)
    review_ids = list(dict.fromkeys(point.review_id for point in points))
    review_rows = list((await db.scalars(select(RequirementReview).where(
        RequirementReview.id.in_(review_ids), RequirementReview.project_id == project_id,
        RequirementReview.status == "approved"))).all()) if review_ids else []
    requirement_module_ids = list(dict.fromkeys(review.requirement_module_id for review in review_rows))
    scenario_data = ScenarioCreate(name=proposal.name, description=proposal.description, priority=proposal.priority,
        requirement_module_ids=requirement_module_ids, steps=[{
            "seq": step.seq, "name": step.name, "interface_id": step.interface_id,
            "request_override": {"candidate_test_data_refs": step.test_data_refs} if step.test_data_refs else {},
            "preconditions": [], "extracts": [], "assertions": [item.model_dump(exclude_none=True) for item in step.assertions],
            "expected_result": step.expected_result, "timeout_ms": step.timeout_ms,
            "retry_count": 0, "continue_on_failure": False,
        } for step in proposal.steps])
    scenario = await scenarios.create(db, project_id, user, scenario_data)
    for point_id in proposal.requirement_test_point_ids:
        db.add(RequirementCoverage(project_id=project_id, test_point_id=point_id, scenario_type="api",
            scenario_id=scenario["id"], status="CANDIDATE", created_by=user.id))
    row.status, row.confirmed_asset_id, row.revision = "superseded", scenario["id"], row.revision + 1
    await db.commit()
    return {"candidate": view(row), "scenario": scenario, "created": True}
