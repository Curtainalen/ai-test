import asyncio
import json
import re

from sqlalchemy import select

from app.database import worker_db_session
from app.models import ApiInterface, ApiScenarioCandidate, ContentBlock, ModelConfig, RequirementDataItem, RequirementModule, RequirementTestCase
from app.models.requirement_ai import RequirementReview, RequirementTestPoint
from app.schemas.ai import ApiScenarioProposal, RequirementReviewPayload, RequirementTestCaseBatchPayload
from pydantic import ValidationError
from app.services.llm import DefaultLlmGateway
from app.services.requirement_reviews import response_schema


def _data_catalog(items: list[RequirementDataItem]) -> list[dict]:
    """Expose only metadata and references; values never enter an LLM prompt."""
    return [{
        "key": item.name,
        "data_type": item.data_type,
        "sensitivity": "secret" if item.sensitive else "internal",
        "reference": item.value_ref,
        "source_block_seq": item.source_block_seq,
        "status": item.status,
    } for item in items]


def _priority_from_strategy(strategy: str, case: dict) -> str:
    if strategy == "all_high":
        return "high"
    if strategy == "all_medium":
        return "medium"
    text = " ".join(str(case.get(key, "")) for key in ("stable_key", "title", "expected_result")).lower()
    if any(word in text for word in ("security", "权限", "越权", "注入", "泄露", "删除", "支付")):
        return "critical"
    if any(word in text for word in ("login", "登录", "token", "认证", "密码", "核心")):
        return "high"
    if any(word in text for word in ("compatibility", "兼容", "浏览器")):
        return "low"
    return "medium"


def _normalize_case_payload(value: object, case_types: list[str] | None = None,
                            priority_strategy: str = "risk_based") -> tuple[dict, str | None]:
    """Normalize legacy field names and scalar steps without adding business facts."""
    if not isinstance(value, dict):
        raise ValueError("响应根对象必须为 JSON 对象")
    normalized_from = None
    if isinstance(value.get("cases"), list):
        normalized = dict(value)
    elif isinstance(value.get("test_cases"), list):
        normalized = dict(value)
        normalized["cases"] = normalized.pop("test_cases")
        normalized_from = "test_cases_to_cases"
    else:
        raise ValueError("结构化响应缺少字段 $.cases")
    allowed_types = case_types or ["normal"]
    type_aliases = {"exception": "abnormal", "异常": "abnormal", "正常": "normal", "边界": "boundary", "权限": "permission", "安全": "security", "兼容": "compatibility"}
    priority_aliases = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}
    changed = bool(normalized_from)
    cases = []
    for index, raw_case in enumerate(normalized["cases"], 1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"$.cases[{index - 1}] 必须为对象")
        case = dict(raw_case)
        raw_type = case.get("case_type", case.get("type"))
        case_type = type_aliases.get(str(raw_type), raw_type)
        if case_type not in allowed_types:
            case_type = allowed_types[0]
            changed = True
        case["case_type"] = case_type
        raw_priority = priority_aliases.get(str(case.get("priority")), case.get("priority"))
        if raw_priority not in {"low", "medium", "high", "critical"}:
            raw_priority = _priority_from_strategy(priority_strategy, case)
            changed = True
        case["priority"] = raw_priority
        case.setdefault("preconditions", [])
        case.setdefault("test_data_refs", [])
        case.setdefault("expected_result", "结果符合已批准测试点的预期")
        raw_steps = case.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError(f"$.cases[{index - 1}].steps 必须为数组")
        steps = []
        for step_index, raw_step in enumerate(raw_steps, 1):
            if isinstance(raw_step, str):
                steps.append({"seq": step_index, "action": raw_step, "input": "", "expected_result": "步骤执行成功"})
                changed = True
            elif isinstance(raw_step, dict):
                step = dict(raw_step)
                step.setdefault("seq", step_index)
                step.setdefault("input", "")
                step.setdefault("expected_result", "步骤执行成功")
                steps.append(step)
            else:
                raise ValueError(f"$.cases[{index - 1}].steps[{step_index - 1}] 格式无效")
        case["steps"] = steps
        cases.append(case)
    return {"cases": cases}, "legacy_payload_normalized" if changed else None


def _validate_case_scope(payload: RequirementTestCaseBatchPayload, allowed_refs: set[str]) -> None:
    for case in payload.cases:
        unknown = set(case.test_data_refs) - allowed_refs
        if unknown:
            raise ValueError(f"测试用例引用不存在于数据目录：{', '.join(sorted(unknown))}")
        for step in case.steps:
            # Prompt output is intended for human review, never a script runner.
            if any(marker in f"{step.action}\n{step.input}".lower() for marker in ("```", "<script", "select ", "insert ", "delete ", "drop ")):
                raise ValueError("测试步骤不能包含脚本、SQL 或生产操作")


def _safe_error_message(exc: Exception) -> str:
    """Keep an actionable error path without returning model-provided secret values."""
    if isinstance(exc, ValidationError):
        labels = {"case_type": "测试类型", "priority": "优先级", "steps": "测试步骤", "stable_key": "用例标识", "title": "用例名称", "expected_result": "预期结果"}
        problems = []
        for error in exc.errors():
            location = error.get("loc", ())
            field = next((str(item) for item in reversed(location) if isinstance(item, str) and item in labels), "结构")
            problem = f"{labels[field]}{'格式无效' if error.get('type') != 'missing' else '缺失'}"
            if problem not in problems:
                problems.append(problem)
            if len(problems) == 3:
                break
        return "模型返回的测试用例结构不完整：" + "、".join(problems or ["字段格式无效"]) + "。请调整生成配置后重试。"
    value = str(getattr(exc, "message", exc))[:1000]
    value = re.sub(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)", r"\1\2******", value)
    return value


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
        # 已确认正文的下游 AI 只读取已确认数据引用，避免把未审核候选带入 Prompt。
        data_items = list((await db.scalars(select(RequirementDataItem).where(
            RequirementDataItem.project_id == row.project_id,
            RequirementDataItem.document_version_id == module.document_version_id,
            RequirementDataItem.status == "confirmed",
        ))).all())
        data_catalog = _data_catalog(data_items)
        allowed_refs = {item["reference"] for item in data_catalog}
        sources = "\n".join(f"[块类型:{block.block_type}] [来源:{json.dumps(block.source_locator, ensure_ascii=False)}]\n{block.content}" for block in blocks)
        prompt = ("仅基于以下已确认模块、来源正文和数据目录生成可测性评审。覆盖正常、异常、边界、权限、一致性和安全风险；不得猜测接口、状态码或页面元素。"
                  "只输出 JSON 对象，根字段必须为 test_points。test_data_refs 只能引用 data_catalog 中存在的 secret:// 或 data:// 引用。\n"
                  f"module={json.dumps({'name': module.name, 'description': module.description}, ensure_ascii=False)}\n"
                  f"source={json.dumps([{'seq': block.seq, 'type': block.block_type, 'content': block.content} for block in blocks], ensure_ascii=False)}\n"
                  f"data_catalog={json.dumps(data_catalog, ensure_ascii=False)}")
        try:
            row.progress, row.current_step = 35, "生成可测性评审"
            await db.commit()
            result = await DefaultLlmGateway(db).generate(project_id=row.project_id, model_config_id=config.id,
                prompt=prompt, response_schema=response_schema(), timeout_ms=min(config.timeout_seconds * 1000, 120000),
                created_by=row.created_by, purpose="requirement_review")
            payload = RequirementReviewPayload.model_validate(result.data)
            unknown_refs = {ref for point in payload.test_points for ref in point.test_data_refs} - allowed_refs
            if unknown_refs:
                raise ValueError(f"测试点引用不存在于数据目录：{', '.join(sorted(unknown_refs))}")
            await db.refresh(row)
            if row.cancel_requested or row.status == "canceled":
                return
            for item in payload.test_points:
                db.add(RequirementTestPoint(project_id=row.project_id, review_id=row.id, created_by=row.created_by, **item.model_dump()))
            row.ambiguities, row.acceptance_suggestions = payload.ambiguities, payload.acceptance_suggestions
            # Preserve numeric scores and normalize qualitative dimensions for the UI.
            row.summary, row.recommendations = payload.summary, payload.recommendations
            row.scores = {key: ({"low": 25, "medium": 60, "high": 90}.get(value, value) if isinstance(value, str) else value) for key, value in payload.scores.items()}
            row.issues = [item.model_dump() for item in payload.issues]
            row.model_config_revision_id, row.llm_call_id, row.status = result.model_config_revision_id, result.call_id, "pending_review"
            row.progress, row.current_step = 100, "等待人工审核"
        except Exception as exc:
            row.status, row.error_code, row.error_message = "failed", getattr(exc, "code", "REQUIREMENT_REVIEW_FAILED"), str(getattr(exc, "message", exc))[:1000]
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
        review = await db.get(RequirementReview, seed.review_id) if seed.review_id else None
        module = await db.get(RequirementModule, seed.requirement_module_id)
        config = await db.get(ModelConfig, seed.model_config_id)
        # 新链路的最小可信输入是“已确认模块”；历史用例才额外要求已批准评审。
        if (review is not None and review.status != "approved") or not module or module.status != "confirmed" or not config or not config.is_enabled:
            seed.status, seed.error_code, seed.error_message = "failed", "MODULE_OR_MODEL_UNAVAILABLE", "已确认需求模块或模型配置不可用"
            await db.commit(); return
        points = list((await db.scalars(select(RequirementTestPoint).where(RequirementTestPoint.review_id == review.id))).all()) if review else []
        blocks = list((await db.scalars(select(ContentBlock).where(
            ContentBlock.project_id == seed.project_id,
            ContentBlock.document_version_id == module.document_version_id,
            ContentBlock.id.in_(set(module.source_block_ids or [])),
        ).order_by(ContentBlock.seq))).all())
        # 测试用例生成同样只能使用已确认的 secret:// / data:// 引用。
        data_items = list((await db.scalars(select(RequirementDataItem).where(
            RequirementDataItem.project_id == seed.project_id,
            RequirementDataItem.document_version_id == module.document_version_id,
            RequirementDataItem.status == "confirmed",
        ))).all())
        data_catalog = _data_catalog(data_items)
        options = getattr(seed, "generation_options", None) or {}
        selected_case_types = [item for item in options.get("case_types", []) if item in {"normal", "abnormal", "boundary", "permission", "security", "compatibility"}] or ["normal", "abnormal", "boundary", "permission", "security", "compatibility"]
        priority_strategy = options.get("priority_strategy") if options.get("priority_strategy") in {"risk_based", "all_high", "all_medium"} else "risk_based"
        source = {
            "confirmed_module": {"name": module.name, "description": module.description},
            "source_blocks": [{"seq": block.seq, "type": block.block_type, "content": block.content} for block in blocks],
            "data_catalog": data_catalog,
            "generation_scope": {"requirement_module_id": module.id, "case_types": selected_case_types, "priority_strategy": priority_strategy},
        }
        if review:
            # 仅兼容历史评审生成的用例；新流程不会创建或依赖该中间层。
            source["historical_review"] = {"summary": review.summary, "issues": review.issues, "acceptance_suggestions": review.acceptance_suggestions, "recommendations": review.recommendations}
            source["historical_test_points"] = [{"stable_key": p.stable_key, "title": p.title, "preconditions": p.preconditions, "test_data_refs": p.test_data_refs, "expected_result": p.expected_result, "risk": p.risk} for p in points]
        try:
            result = await DefaultLlmGateway(db).generate(project_id=seed.project_id, model_config_id=config.id,
                # 模块已由人工确认，模型只负责生成候选；候选仍需人工确认后才能进入自动化。
                prompt="只能基于 confirmed_module、source_blocks、data_catalog、generation_scope 生成测试用例候选。只使用 generation_scope.case_types 中的类型，并按 priority_strategy 评定优先级。禁止编造接口、页面、字段、账号、密码或 Token。只输出 JSON 对象，根字段必须且只能为 cases；cases 必须非空，stable_key 必须唯一，引用只能来自 data_catalog，步骤不得包含脚本代码。\n" + json.dumps(source, ensure_ascii=False),
                # Alias normalization is performed below, then Pydantic applies the exact contract.
                response_schema={"type": "object"}, timeout_ms=min(config.timeout_seconds * 1000, 120000),
                created_by=seed.created_by, purpose="requirement_test_case")
            normalized, normalization_applied = _normalize_case_payload(result.data, selected_case_types, priority_strategy)
            payload = RequirementTestCaseBatchPayload.model_validate(normalized)
            _validate_case_scope(payload, {item["reference"] for item in data_catalog})
            values = payload.cases
            # 复用占位记录保存首个候选，其余候选作为新记录批量加入。
            first = values[0]
            seed.stable_key, seed.title, seed.case_type, seed.priority = first.stable_key, first.title, first.case_type, first.priority
            seed.preconditions, seed.test_data_refs = first.preconditions, first.test_data_refs
            seed.steps, seed.expected_result = [item.model_dump() for item in first.steps], first.expected_result
            seed.model_config_revision_id, seed.llm_call_id, seed.status, seed.revision = result.model_config_revision_id, result.call_id, "pending_review", seed.revision + 1
            seed.normalization_applied = normalization_applied
            for item in values[1:]:
                db.add(RequirementTestCase(project_id=seed.project_id, document_version_id=seed.document_version_id, requirement_module_id=seed.requirement_module_id, review_id=seed.review_id, model_config_id=seed.model_config_id, model_config_revision_id=result.model_config_revision_id, llm_call_id=result.call_id, stable_key=item.stable_key, title=item.title, case_type=item.case_type, priority=item.priority, preconditions=item.preconditions, test_data_refs=item.test_data_refs, steps=[step.model_dump() for step in item.steps], expected_result=item.expected_result, status="pending_review", created_by=seed.created_by))
        except Exception as exc:
            code = getattr(exc, "code", "LLM_RESPONSE_SCHEMA_INVALID" if isinstance(exc, (ValidationError, ValueError)) else "TEST_CASE_GENERATION_FAILED")
            seed.status, seed.error_code, seed.error_message, seed.revision = "failed", code, _safe_error_message(exc), seed.revision + 1
            seed.title = f"{module.name} · 测试用例生成失败"
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
