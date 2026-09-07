from datetime import UTC, datetime

from sqlalchemy import func, select

from app.errors import AppError
from app.models import DocumentVersion, ModelConfig, RequirementModule, RequirementReview, RequirementTestCase
from app.services.identity import require_membership
from app.services.queue import enqueue_unique


def view(row):
    return {"id": row.id, "review_id": row.review_id, "document_version_id": row.document_version_id,
            "requirement_module_id": row.requirement_module_id, "stable_key": row.stable_key, "title": row.title,
            "case_type": row.case_type, "priority": row.priority, "preconditions": row.preconditions,
            "test_data_refs": row.test_data_refs, "steps": row.steps, "expected_result": row.expected_result,
            "status": row.status, "revision": row.revision, "error_code": row.error_code,
            "error_message": row.error_message, "normalization_applied": getattr(row, "normalization_applied", None),
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}


async def generate(db, project_id, user, data):
    await require_membership(db, project_id, user)
    review = None
    if data.requirement_module_id:
        module = await db.scalar(select(RequirementModule).where(
            RequirementModule.id == data.requirement_module_id,
            RequirementModule.project_id == project_id,
            RequirementModule.status == "confirmed",
        ))
        if module is None:
            raise AppError("REQUIREMENT_MODULE_NOT_CONFIRMED", "只有已确认需求模块可以生成测试用例候选", 409)
        version = await db.get(DocumentVersion, module.document_version_id)
        if not version or version.parse_status != "completed" or version.content_status != "confirmed":
            raise AppError("DOCUMENT_CONTENT_NOT_CONFIRMED", "请先确认已解析的需求正文", 409)
    else:
        # 历史客户端仍可使用评审入口；新页面不会再创建评审记录。
        review = await db.scalar(select(RequirementReview).where(RequirementReview.id == data.review_id, RequirementReview.project_id == project_id))
        if review is None or review.status != "approved":
            raise AppError("REQUIREMENT_REVIEW_NOT_APPROVED", "只有已批准需求评审可以生成测试用例候选", 409)
        module = await db.get(RequirementModule, review.requirement_module_id)
    config_query = select(ModelConfig).where(ModelConfig.is_enabled.is_(True))
    config_query = config_query.where(ModelConfig.id == data.model_config_id) if data.model_config_id else config_query.where(ModelConfig.is_default.is_(True))
    config = await db.scalar(config_query)
    if config is None:
        raise AppError("MODEL_CONFIG_NOT_FOUND", "模型配置不存在或已停用", 404)
    # 先创建一条“生成中”占位用例作为异步任务载体，避免额外暴露一张任务表。
    # 临时 stable_key 用于把后续 AI 结果和本次请求关联起来。
    if module is None:
        raise AppError("REQUIREMENT_MODULE_NOT_FOUND", "需求模块不存在", 404)
    row = RequirementTestCase(project_id=project_id, document_version_id=module.document_version_id,
        requirement_module_id=module.id, review_id=review.id if review else None, model_config_id=config.id,
        stable_key=f"generation-{module.id[:8]}-{int(datetime.now(UTC).timestamp())}", title=f"{module.name} · 正在生成测试用例",
        case_type=data.case_types[0], priority="medium", preconditions=[], test_data_refs=[], steps=[], expected_result="", status="generating",
        generation_options={"case_types": data.case_types, "priority_strategy": data.priority_strategy}, created_by=user.id)
    db.add(row); await db.commit()
    enqueue_unique("app.ai_worker_jobs.generate_requirement_test_cases_job", row.id, 180)
    return view(row)


async def list_cases(db, project_id, user, page, page_size, status=None):
    await require_membership(db, project_id, user)
    stmt = select(RequirementTestCase).where(RequirementTestCase.project_id == project_id)
    if status: stmt = stmt.where(RequirementTestCase.status == status)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(RequirementTestCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size))).all())
    return {"items": [view(row) for row in rows], "page": page, "page_size": page_size, "total": total}


async def decide(db, project_id, user, case_id, data):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(RequirementTestCase).where(RequirementTestCase.id == case_id, RequirementTestCase.project_id == project_id))
    if row is None: raise AppError("RESOURCE_NOT_FOUND", "测试用例候选不存在", 404)
    if row.revision != data.revision: raise AppError("REVISION_CONFLICT", "测试用例已被其他用户修改", 409, {"current_revision": row.revision})
    if row.status != "pending_review": raise AppError("TEST_CASE_NOT_REVIEWABLE", "测试用例不处于待确认状态", 409)
    row.status, row.reviewed_by, row.reviewed_at, row.revision = data.decision, user.id, datetime.now(UTC), row.revision + 1
    await db.commit(); return view(row)


async def confirmed_scope(db, project_id, case_ids):
    rows = list((await db.scalars(select(RequirementTestCase).where(RequirementTestCase.project_id == project_id,
        RequirementTestCase.id.in_(set(case_ids)), RequirementTestCase.status == "confirmed"))).all())
    if len(rows) != len(set(case_ids)):
        raise AppError("TEST_CASE_NOT_CONFIRMED", "测试用例未确认、不存在或不属于当前项目", 422)
    return rows
