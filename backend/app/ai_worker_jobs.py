import asyncio
import json

from sqlalchemy import select

from app.database import worker_db_session
from app.models import ApiInterface, ApiScenarioCandidate, ContentBlock, ModelConfig, RequirementModule, RequirementTestCase
from app.models.requirement_ai import RequirementReview, RequirementTestPoint
from app.schemas.ai import ApiScenarioProposal, RequirementReviewPayload, RequirementTestCaseBatchPayload
from app.services.llm import DefaultLlmGateway
from app.services.requirement_reviews import response_schema


def generate_requirement_review_job(review_id: str) -> None:
    asyncio.run(_generate_requirement_review(review_id))


async def _generate_requirement_review(review_id: str) -> None:
    async with worker_db_session() as db:
        row = await db.get(RequirementReview, review_id)
        if row is None or row.status != "generating":
            return
        row.progress, row.current_step = 10, "校验模块来源"
        await db.commit()
        module = await db.scalar(select(RequirementModule).where(RequirementModule.id == row.requirement_module_id,
                                                                  RequirementModule.project_id == row.project_id))
        config = await db.scalar(select(ModelConfig).where(ModelConfig.id == row.model_config_id, ModelConfig.is_enabled.is_(True)))
        if module is None or config is None:
            row.status, row.error_code, row.error_message = "failed", "MODEL_OR_MODULE_UNAVAILABLE", "需求模块或默认模型不可用"
            await db.commit()
            return
        blocks = list((await db.scalars(select(ContentBlock).where(ContentBlock.project_id == row.project_id, ContentBlock.document_version_id == module.document_version_id, ContentBlock.id.in_(set(module.source_block_ids or []))).order_by(ContentBlock.seq))).all())
        if len(blocks) != len(set(module.source_block_ids or [])):
            row.status, row.error_code, row.error_message = "failed", "INVALID_SOURCE_BLOCK", "模块来源内容块不存在或不属于当前项目"
            await db.commit(); return
        total_length = sum(len(block.content) for block in blocks)
        if total_length > 20000:
            row.status, row.error_code, row.error_message = "failed", "REQUIREMENT_CONTENT_TOO_LARGE", "模块关联正文超过 20000 字符上限"
            await db.commit(); return
        if row.cancel_requested:
            row.status, row.current_step = "canceled", "已取消"
            await db.commit(); return
        sources = "\n".join(f"[块类型:{block.block_type}] [来源:{json.dumps(block.source_locator, ensure_ascii=False)}]\n{block.content}" for block in blocks)
        prompt = ("仅基于以下已确认需求模块及来源正文生成可测性评审。输出必须符合 JSON Schema；测试数据仅使用 secret:// 引用。\n"
                  f"模块名称：{module.name}\n模块说明：{module.description}\n来源正文：\n{sources}")
        try:
            row.progress, row.current_step = 35, "生成可测性评审"
            await db.commit()
            result = await DefaultLlmGateway(db).generate(project_id=row.project_id, model_config_id=config.id,
                prompt=prompt, response_schema=response_schema(), timeout_ms=min(config.timeout_seconds * 1000, 120000),
                created_by=row.created_by, purpose="requirement_review")
            payload = RequirementReviewPayload.model_validate(result.data)
            await db.refresh(row)
            if row.cancel_requested or row.status == "canceled":
                return
            for item in payload.test_points:
                db.add(RequirementTestPoint(project_id=row.project_id, review_id=row.id, created_by=row.created_by, **item.model_dump()))
            row.ambiguities, row.acceptance_suggestions = payload.ambiguities, payload.acceptance_suggestions
            row.summary, row.recommendations, row.scores = payload.summary, payload.recommendations, payload.scores
            row.issues = [item.model_dump() for item in payload.issues]
            row.model_config_revision_id, row.llm_call_id, row.status = result.model_config_revision_id, result.call_id, "pending_review"
            row.progress, row.current_step = 100, "等待人工审核"
        except Exception as exc:
            row.status, row.error_code, row.error_message = "failed", getattr(exc, "code", "REQUIREMENT_REVIEW_FAILED"), "需求评审生成失败"
            row.current_step = "生成失败"
        await db.commit()


def generate_api_scenario_candidate_job(candidate_id: str) -> None:
    asyncio.run(_generate_api_scenario_candidate(candidate_id))


def generate_requirement_test_cases_job(case_id: str) -> None:
    asyncio.run(_generate_requirement_test_cases(case_id))


async def _generate_requirement_test_cases(case_id: str) -> None:
    async with worker_db_session() as db:
        seed = await db.get(RequirementTestCase, case_id)
        if seed is None or seed.status != "generating": return
        review = await db.get(RequirementReview, seed.review_id)
        module = await db.get(RequirementModule, seed.requirement_module_id)
        config = await db.get(ModelConfig, seed.model_config_id)
        if not review or review.status != "approved" or not module or not config or not config.is_enabled:
            seed.status, seed.error_code, seed.error_message = "failed", "REVIEW_OR_MODEL_UNAVAILABLE", "需求评审、模块或模型配置不可用"
            await db.commit(); return
        points = list((await db.scalars(select(RequirementTestPoint).where(RequirementTestPoint.review_id == review.id))).all())
        source = {"module": {"name": module.name, "description": module.description}, "review": {"summary": review.summary, "issues": review.issues, "acceptance_suggestions": review.acceptance_suggestions}, "test_points": [{"title": p.title, "preconditions": p.preconditions, "expected_result": p.expected_result, "risk": p.risk} for p in points]}
        try:
            result = await DefaultLlmGateway(db).generate(project_id=seed.project_id, model_config_id=config.id,
                prompt="仅基于已批准需求评审生成结构化测试用例候选。覆盖正常、异常、边界、权限和一致性情形；步骤必须可人工审阅，测试数据只能使用 secret:// 引用。输出必须符合 JSON Schema。\n" + json.dumps(source, ensure_ascii=False),
                response_schema=RequirementTestCaseBatchPayload.model_json_schema(), timeout_ms=min(config.timeout_seconds * 1000, 120000),
                created_by=seed.created_by, purpose="requirement_test_case")
            payload = RequirementTestCaseBatchPayload.model_validate(result.data)
            values = payload.cases
            # 复用占位记录保存首个候选，其余候选作为新记录批量加入。
            first = values[0]
            seed.stable_key, seed.title, seed.case_type, seed.priority = first.stable_key, first.title, first.case_type, first.priority
            seed.preconditions, seed.test_data_refs = first.preconditions, first.test_data_refs
            seed.steps, seed.expected_result = [item.model_dump() for item in first.steps], first.expected_result
            seed.model_config_revision_id, seed.llm_call_id, seed.status, seed.revision = result.model_config_revision_id, result.call_id, "pending_review", seed.revision + 1
            for item in values[1:]:
                db.add(RequirementTestCase(project_id=seed.project_id, document_version_id=seed.document_version_id, requirement_module_id=seed.requirement_module_id, review_id=seed.review_id, model_config_id=seed.model_config_id, model_config_revision_id=result.model_config_revision_id, llm_call_id=result.call_id, stable_key=item.stable_key, title=item.title, case_type=item.case_type, priority=item.priority, preconditions=item.preconditions, test_data_refs=item.test_data_refs, steps=[step.model_dump() for step in item.steps], expected_result=item.expected_result, status="pending_review", created_by=seed.created_by))
        except Exception as exc:
            seed.status, seed.error_code, seed.error_message, seed.revision = "failed", getattr(exc, "code", "TEST_CASE_GENERATION_FAILED"), "测试用例候选生成失败", seed.revision + 1
        await db.commit()


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
            cases = list((await db.scalars(select(RequirementTestCase).where(
                RequirementTestCase.project_id == row.project_id,
                RequirementTestCase.id.in_(set(row.requirement_test_case_ids)), RequirementTestCase.status == "confirmed",
            ))).all()) if row.requirement_test_case_ids else []
            config = await db.scalar(select(ModelConfig).where(
                ModelConfig.id == row.model_config_id, ModelConfig.is_enabled.is_(True)))
            if len(interfaces) != len(set(row.interface_ids)) or len(cases) != len(set(row.requirement_test_case_ids)) or config is None:
                row.status, row.error_code, row.error_message = "failed", "API_CANDIDATE_SOURCE_UNAVAILABLE", "接口、已确认测试用例或模型配置不可用"
                await db.commit()
                return
            source = {
                "interfaces": [{
                    "id": item.id, "method": item.method, "path": item.path,
                    "summary": item.summary, "parameters": item.parameters,
                    "request_body": item.request_body, "responses": item.responses,
                } for item in interfaces],
                "requirement_test_cases": [{
                    "id": item.id, "title": item.title, "steps": item.steps,
                    "preconditions": item.preconditions,
                    "expected_result": item.expected_result, "case_type": item.case_type,
                } for item in cases],
            }
            prompt = (
                "仅基于以下接口资产和已确认需求测试用例，生成一个 API 测试场景候选。"
                "只能引用 source 中的 interface id 和 requirement test case id；"
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
                point_scope = set(row.requirement_test_case_ids)
                if any(step.interface_id not in interface_scope for step in proposal.steps) or any(
                    point_id not in point_scope for point_id in proposal.requirement_test_case_ids
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
