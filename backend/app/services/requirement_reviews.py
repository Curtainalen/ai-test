from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.errors import AppError
from app.models import ModelConfig, RequirementModule, TestScenario, UiScenario
from app.models.requirement_ai import RequirementCoverage, RequirementReview, RequirementTestPoint
from app.schemas.ai import RequirementReviewPayload
from app.services.identity import require_membership
from app.services.queue import enqueue_unique


def view(row, points=None, module=None):
    data = {"id": row.id, "project_id": row.project_id, "requirement_module_id": row.requirement_module_id,
            "requirement_module_revision": row.requirement_module_revision, "model_config_id": row.model_config_id, "revision": row.revision,
            "status": row.status, "ambiguities": row.ambiguities, "acceptance_suggestions": row.acceptance_suggestions,
            "summary": getattr(row, "summary", ""), "recommendations": getattr(row, "recommendations", []),
            "scores": getattr(row, "scores", {}), "issues": getattr(row, "issues", []),
            "progress": getattr(row, "progress", 0), "current_step": getattr(row, "current_step", ""),
            "model_config_revision_id": row.model_config_revision_id, "llm_call_id": row.llm_call_id,
            "error_code": row.error_code, "error_message": row.error_message,
            "created_by": row.created_by, "created_at": row.created_at.isoformat() if row.created_at else None}
    if module is not None:
        data["module_name"] = module.name
        data["module_status"] = module.status
    if points is not None:
        data["test_points"] = [{"id": item.id, "stable_key": item.stable_key, "title": item.title,
                                "preconditions": item.preconditions, "test_data_refs": item.test_data_refs,
                                "expected_result": item.expected_result, "risk": item.risk} for item in points]
    return data


async def create(db, project_id, user, data):
    await require_membership(db, project_id, user)
    module = await db.scalar(select(RequirementModule).where(RequirementModule.id == data.requirement_module_id,
                                                              RequirementModule.project_id == project_id))
    if module is None:
        raise AppError("RESOURCE_NOT_FOUND", "需求模块不存在", 404)
    if module.status != "confirmed":
        raise AppError("REQUIREMENT_MODULE_NOT_CONFIRMED", "只有已确认需求模块可以评审", 409)
    config_stmt = select(ModelConfig).where(ModelConfig.is_enabled.is_(True))
    config_stmt = config_stmt.where(ModelConfig.id == data.model_config_id) if data.model_config_id else config_stmt.where(ModelConfig.is_default.is_(True))
    config = await db.scalar(config_stmt)
    if config is None:
        raise AppError("MODEL_CONFIG_NOT_FOUND", "模型配置不存在或已停用", 404)
    revision = int(await db.scalar(select(func.max(RequirementReview.revision)).where(
        RequirementReview.project_id == project_id, RequirementReview.requirement_module_id == module.id)) or 0) + 1
    row = RequirementReview(project_id=project_id, requirement_module_id=module.id,
                            requirement_module_revision=module.revision, model_config_id=config.id, revision=revision,
                            status="generating", progress=0, current_step="等待生成", created_by=user.id)
    db.add(row)
    await db.commit()
    enqueue_unique("app.ai_worker_jobs.generate_requirement_review_job", row.id, 180)
    return view(row, [])


async def detail(db, project_id, user, review_id):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementReview).where(RequirementReview.id == review_id, RequirementReview.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "需求评审不存在", 404)
    points = list((await db.scalars(select(RequirementTestPoint).where(
        RequirementTestPoint.project_id == project_id, RequirementTestPoint.review_id == row.id).order_by(RequirementTestPoint.stable_key))).all())
    module = await db.scalar(select(RequirementModule).where(RequirementModule.id == row.requirement_module_id, RequirementModule.project_id == project_id))
    return view(row, points, module)


async def list_reviews(db, project_id, user, page: int, page_size: int):
    await require_membership(db, project_id, user)
    stmt = select(RequirementReview).where(RequirementReview.project_id == project_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(RequirementReview.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all())
    modules = {row.id: row for row in (await db.scalars(select(RequirementModule).where(RequirementModule.project_id == project_id, RequirementModule.id.in_({item.requirement_module_id for item in rows})))).all()} if rows else {}
    return {"items": [view(row, module=modules.get(row.requirement_module_id)) for row in rows], "page": page, "page_size": page_size, "total": total}


async def decide(db, project_id, user, review_id, decision):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementReview).where(RequirementReview.id == review_id, RequirementReview.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "需求评审不存在", 404)
    if row.status != "pending_review":
        raise AppError("REQUIREMENT_REVIEW_NOT_REVIEWABLE", "评审不处于待审核状态", 409)
    row.status, row.reviewed_by, row.reviewed_at = decision, user.id, datetime.now(UTC)
    await db.commit()
    return await detail(db, project_id, user, row.id)


async def cancel(db, project_id, user, review_id):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementReview).where(RequirementReview.id == review_id,
        RequirementReview.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "需求评审不存在", 404)
    if row.status != "generating":
        raise AppError("REQUIREMENT_REVIEW_NOT_CANCELABLE", "只有生成中的评审可以取消", 409)
    row.cancel_requested, row.status, row.current_step = True, "canceled", "已取消"
    await db.commit()
    return await detail(db, project_id, user, row.id)


def response_schema():
    return RequirementReviewPayload.model_json_schema()


def coverage_view(row, point=None, module=None, scenario=None):
    data = {"id": row.id, "test_point_id": row.test_point_id, "scenario_type": row.scenario_type,
            "scenario_id": row.scenario_id, "execution_report_id": row.execution_report_id,
            "status": row.status, "revision": row.revision}
    if point: data["test_point_title"] = point.title
    if module: data["module_name"] = module.name
    if scenario: data["scenario_name"] = scenario.name
    return data


async def create_coverage(db, project_id, user, data):
    await require_membership(db, project_id, user)
    point = await db.scalar(select(RequirementTestPoint).join(RequirementReview, RequirementReview.id == RequirementTestPoint.review_id).where(
        RequirementTestPoint.id == data.test_point_id, RequirementTestPoint.project_id == project_id,
        RequirementReview.project_id == project_id, RequirementReview.status == "approved"))
    model = TestScenario if data.scenario_type == "api" else UiScenario
    scenario = await db.scalar(select(model).where(model.id == data.scenario_id, model.project_id == project_id))
    if point is None or scenario is None:
        raise AppError("REQUIREMENT_COVERAGE_REFERENCE_INVALID", "测试点或场景不存在、未批准或跨项目", 422)
    existing = await db.scalar(select(RequirementCoverage).where(RequirementCoverage.project_id == project_id,
        RequirementCoverage.test_point_id == point.id, RequirementCoverage.scenario_type == data.scenario_type,
        RequirementCoverage.scenario_id == scenario.id))
    if existing:
        return coverage_view(existing)
    row = RequirementCoverage(project_id=project_id, test_point_id=point.id, scenario_type=data.scenario_type,
        scenario_id=scenario.id, status="CONFIRMED", created_by=user.id)
    db.add(row)
    await db.commit()
    return coverage_view(row)


async def list_coverages(db, project_id, user, page, page_size):
    await require_membership(db, project_id, user)
    stmt = select(RequirementCoverage).where(RequirementCoverage.project_id == project_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(RequirementCoverage.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).all())
    points = {row.id: row for row in (await db.scalars(select(RequirementTestPoint).where(RequirementTestPoint.project_id == project_id, RequirementTestPoint.id.in_({item.test_point_id for item in rows})))).all()} if rows else {}
    reviews = {row.id: row for row in (await db.scalars(select(RequirementReview).where(RequirementReview.project_id == project_id, RequirementReview.id.in_({point.review_id for point in points.values()})))).all()} if points else {}
    modules = {row.id: row for row in (await db.scalars(select(RequirementModule).where(RequirementModule.project_id == project_id, RequirementModule.id.in_({review.requirement_module_id for review in reviews.values()})))).all()} if reviews else {}
    api_ids = {item.scenario_id for item in rows if item.scenario_type == "api"}; ui_ids = {item.scenario_id for item in rows if item.scenario_type == "ui"}
    api_scenarios = {row.id: row for row in (await db.scalars(select(TestScenario).where(TestScenario.project_id == project_id, TestScenario.id.in_(api_ids)))).all()} if api_ids else {}
    ui_scenarios = {row.id: row for row in (await db.scalars(select(UiScenario).where(UiScenario.project_id == project_id, UiScenario.id.in_(ui_ids)))).all()} if ui_ids else {}
    return {"items": [coverage_view(row, points.get(row.test_point_id), modules.get(reviews.get(points.get(row.test_point_id).review_id).requirement_module_id) if points.get(row.test_point_id) else None, (api_scenarios if row.scenario_type == "api" else ui_scenarios).get(row.scenario_id)) for row in rows], "page": page, "page_size": page_size, "total": total}


async def list_approved_test_points(db, project_id, user, page, page_size):
    await require_membership(db, project_id, user)
    scope = select(RequirementTestPoint, RequirementReview, RequirementModule).join(
        RequirementReview, RequirementReview.id == RequirementTestPoint.review_id
    ).join(
        RequirementModule, RequirementModule.id == RequirementReview.requirement_module_id
    ).where(
        RequirementTestPoint.project_id == project_id,
        RequirementReview.project_id == project_id,
        RequirementReview.status == "approved",
    )
    total = int(await db.scalar(select(func.count()).select_from(scope.subquery())) or 0)
    rows = list((await db.execute(scope.order_by(RequirementTestPoint.created_at.desc()).offset(
        (page - 1) * page_size).limit(page_size))).all())
    return {
        "items": [{"id": point.id, "review_id": point.review_id, "stable_key": point.stable_key,
                   "title": point.title, "expected_result": point.expected_result, "risk": point.risk,
                   "module_id": module.id, "module_name": module.name}
                  for point, _review, module in rows],
        "page": page, "page_size": page_size, "total": total,
    }
