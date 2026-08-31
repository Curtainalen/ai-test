import asyncio
import json

from sqlalchemy import select

from app.database import worker_db_session
from app.models import ApiInterface, ApiScenarioCandidate, ModelConfig, RequirementModule
from app.models.requirement_ai import RequirementReview, RequirementTestPoint
from app.schemas.ai import ApiScenarioProposal, RequirementReviewPayload
from app.services.llm import DefaultLlmGateway
from app.services.requirement_reviews import response_schema


def generate_requirement_review_job(review_id: str) -> None:
    asyncio.run(_generate_requirement_review(review_id))


async def _generate_requirement_review(review_id: str) -> None:
    async with worker_db_session() as db:
        row = await db.get(RequirementReview, review_id)
        if row is None or row.status != "generating":
            return
        module = await db.scalar(select(RequirementModule).where(RequirementModule.id == row.requirement_module_id,
                                                                  RequirementModule.project_id == row.project_id))
        config = await db.scalar(select(ModelConfig).where(ModelConfig.id == row.model_config_id, ModelConfig.is_enabled.is_(True)))
        if module is None or config is None:
            row.status, row.error_code, row.error_message = "failed", "MODEL_OR_MODULE_UNAVAILABLE", "需求模块或默认模型不可用"
            await db.commit()
            return
        prompt = ("仅基于以下已确认需求模块生成可测性评审。输出必须符合 JSON Schema；测试数据仅使用 secret:// 引用。\n"
                  f"模块名称：{module.name}\n模块说明：{module.description}")
        try:
            result = await DefaultLlmGateway(db).generate(project_id=row.project_id, model_config_id=config.id,
                prompt=prompt, response_schema=response_schema(), timeout_ms=min(config.timeout_seconds * 1000, 120000),
                created_by=row.created_by, purpose="requirement_review")
            payload = RequirementReviewPayload.model_validate(result.data)
            for item in payload.test_points:
                db.add(RequirementTestPoint(project_id=row.project_id, review_id=row.id, created_by=row.created_by, **item.model_dump()))
            row.ambiguities, row.acceptance_suggestions = payload.ambiguities, payload.acceptance_suggestions
            row.model_config_revision_id, row.llm_call_id, row.status = result.model_config_revision_id, result.call_id, "pending_review"
        except Exception as exc:
            row.status, row.error_code, row.error_message = "failed", getattr(exc, "code", "REQUIREMENT_REVIEW_FAILED"), "需求评审生成失败"
        await db.commit()


def generate_api_scenario_candidate_job(candidate_id: str) -> None:
    asyncio.run(_generate_api_scenario_candidate(candidate_id))


async def _watch_api_candidate_cancel(candidate_id: str, cancellation: asyncio.Event) -> None:
    while not cancellation.is_set():
        await asyncio.sleep(0.5)
        async with worker_db_session() as watch_db:
            row = await watch_db.get(ApiScenarioCandidate, candidate_id)
            if row is None or row.cancel_requested or row.status != "generating":
                cancellation.set()
                return


async def _generate_api_scenario_candidate(candidate_id: str) -> None:
    cancellation = asyncio.Event()
    watcher = asyncio.create_task(_watch_api_candidate_cancel(candidate_id, cancellation))
    try:
        async with worker_db_session() as db:
            row = await db.get(ApiScenarioCandidate, candidate_id)
            if row is None or row.status != "generating":
                return
            interfaces = list((await db.scalars(select(ApiInterface).where(
                ApiInterface.project_id == row.project_id,
                ApiInterface.id.in_(set(row.interface_ids)),
                ApiInterface.is_deleted.is_(False),
            ))).all())
            points = list((await db.scalars(select(RequirementTestPoint).where(
                RequirementTestPoint.project_id == row.project_id,
                RequirementTestPoint.id.in_(set(row.requirement_test_point_ids)),
            ))).all()) if row.requirement_test_point_ids else []
            config = await db.scalar(select(ModelConfig).where(
                ModelConfig.id == row.model_config_id, ModelConfig.is_enabled.is_(True)))
            if len(interfaces) != len(set(row.interface_ids)) or len(points) != len(set(row.requirement_test_point_ids)) or config is None:
                row.status, row.error_code, row.error_message = "failed", "API_CANDIDATE_SOURCE_UNAVAILABLE", "接口、测试点或模型配置不可用"
                await db.commit()
                return
            source = {
                "interfaces": [{
                    "id": item.id, "method": item.method, "path": item.path,
                    "summary": item.summary, "parameters": item.parameters,
                    "request_body": item.request_body, "responses": item.responses,
                } for item in interfaces],
                "requirement_test_points": [{
                    "id": item.id, "title": item.title,
                    "preconditions": item.preconditions,
                    "expected_result": item.expected_result, "risk": item.risk,
                } for item in points],
            }
            prompt = (
                "仅基于以下接口资产和已批准需求测试点，生成一个 API 测试场景候选。"
                "只能引用 source 中的 interface id 和 requirement test point id；"
                "测试数据只能使用 secret:// 引用，不得输出脚本、代码或生产性操作。"
                "输出必须严格符合 JSON Schema。\n"
                f"用户意图：{row.instruction}\nsource={json.dumps(source, ensure_ascii=False)}"
            )
            try:
                result = await DefaultLlmGateway(db).generate(
                    project_id=row.project_id, model_config_id=config.id, prompt=prompt,
                    response_schema=ApiScenarioProposal.model_json_schema(),
                    timeout_ms=min(config.timeout_seconds * 1000, 120000),
                    cancellation_token=cancellation, created_by=row.created_by,
                    purpose="api_scenario_candidate",
                )
                proposal = ApiScenarioProposal.model_validate(result.data)
                interface_scope = set(row.interface_ids)
                point_scope = set(row.requirement_test_point_ids)
                if any(step.interface_id not in interface_scope for step in proposal.steps) or any(
                    point_id not in point_scope for point_id in proposal.requirement_test_point_ids
                ):
                    raise ValueError("candidate references sources outside the approved scope")
                await db.refresh(row)
                if row.cancel_requested or row.status != "generating":
                    return
                row.content = {"proposal": proposal.model_dump(mode="json")}
                row.model_config_revision_id = result.model_config_revision_id
                row.llm_call_id = result.call_id
                row.status = "pending_review"
                row.revision += 1
            except Exception as exc:
                await db.refresh(row)
                if row.cancel_requested or row.status == "canceled":
                    return
                row.status = "failed"
                row.error_code = getattr(exc, "code", "API_CANDIDATE_GENERATION_FAILED")
                row.error_message = "API 场景候选生成失败"
                row.revision += 1
            await db.commit()
    finally:
        cancellation.set()
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
