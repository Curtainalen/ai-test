from __future__ import annotations

import json
from copy import deepcopy

import httpx
from sqlalchemy import select

from app.errors import AppError
from app.models import ModelConfig, UiAutomationCandidate, UiExecutionStep, UiExplorationSession, UiExplorationStep
from app.security import decrypt_secret
from app.services.llm_probe import ANTHROPIC, GEMINI, OPENAI_CHAT, ProbeRequest, build_probe_request
from app.services.masking import mask_data
from app.services.ui_assets import _one
from app.schemas.ui import UiAutomationBundle, UiRepairProposal
from app.services.llm import DefaultLlmGateway

SYSTEM_PROMPT = """你是测试平台的 UI 自动化候选生成器。仅输出一个 JSON 对象，不要输出 Markdown。
你只能提出候选，绝不能声明已验证、已保存、已执行或建议绕过审批。
禁止输出密码、token、cookie、authorization、个人信息、脚本、坐标点击或外部 URL。
locator 候选优先级：data-testid/stable id，role+name，label/name/placeholder，稳定 CSS，XPath。
当 candidate_type 为 automation_bundle 时，必须输出：module_name、module_description、pages、elements、page_steps、scenario_name、scenario_description、scenario_step_keys。所有引用使用同一候选内的 key；页面步骤只使用 navigate/click/fill/select/hover/press/check/uncheck/visible/text/url/wait_for；敏感输入只能是 secret:// 引用。
"""


def _message_content(payload: dict, protocol: str):
    if protocol == OPENAI_CHAT:
        choices = payload.get("choices") or []
        return (choices[0].get("message") or {}).get("content") if choices else None
    if protocol == ANTHROPIC:
        content = payload.get("content") or []
        return content[0].get("text") if content else None
    candidates = payload.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    return parts[0].get("text") if parts else None


def _request(config, api_key: str, prompt: str):
    base = build_probe_request(config, api_key)
    if config.protocol == OPENAI_CHAT:
        payload = {"model": config.model_name, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], "temperature": 0, "max_tokens": 1200, "response_format": {"type": "json_object"}, "stream": False}
    elif config.protocol == ANTHROPIC:
        payload = {"model": config.model_name, "max_tokens": 1200, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": prompt}]}
    else:
        payload = {"contents": [{"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n{prompt}"}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 1200, "responseMimeType": "application/json"}}
    return ProbeRequest(url=base.url, headers=base.headers, payload=payload)


async def _source_context(db, candidate: UiAutomationCandidate) -> dict:
    context: dict = {"instruction": (candidate.content or {}).get("instruction", ""), "candidate_type": candidate.candidate_type}
    if candidate.exploration_id:
        session = await _one(db, UiExplorationSession, candidate.project_id, candidate.exploration_id, "探索会话")
        steps = list((await db.scalars(select(UiExplorationStep).where(UiExplorationStep.exploration_id == session.id).order_by(UiExplorationStep.seq))).all())
        context["exploration"] = {
            "goal": session.goal, "start_url": session.start_url, "status": session.status,
            "requirement_test_point_ids": session.requirement_test_point_ids,
            "current_url": session.current_url, "dom_summary": session.dom_summary,
            "steps": [{"operation": step.operation, "status": step.status, "actual_url": step.actual_url,
                        "dom_summary": step.dom_summary, "error_code": step.error_code} for step in steps],
        }
    if candidate.execution_id:
        steps = list((await db.scalars(select(UiExecutionStep).where(UiExecutionStep.execution_id == candidate.execution_id).order_by(UiExecutionStep.seq))).all())
        context["execution"] = {"steps": [{"name": step.name, "status": step.status,
                                               "action": step.action_snapshot, "result": step.result_snapshot,
                                               "error_category": step.error_category} for step in steps]}
    return mask_data(deepcopy(context))


async def generate_candidate(db, candidate: UiAutomationCandidate) -> dict:
    config = await db.scalar(select(ModelConfig).where(ModelConfig.is_default.is_(True), ModelConfig.is_enabled.is_(True)))
    if config is None or not config.api_key_encrypted:
        raise AppError("UI_MODEL_NOT_CONFIGURED", "没有可用的默认模型配置", 422)
    context = await _source_context(db, candidate)
    prompt = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    schema = (UiAutomationBundle.model_json_schema() if candidate.candidate_type == "automation_bundle"
              else UiRepairProposal.model_json_schema() if candidate.candidate_type == "repair" else {"type": "object"})
    result = await DefaultLlmGateway(db).generate(project_id=candidate.project_id, model_config_id=config.id,
        prompt=f"{SYSTEM_PROMPT}\n{prompt}", response_schema=schema, timeout_ms=config.timeout_seconds * 1000,
        created_by=candidate.created_by, purpose=f"ui_{candidate.candidate_type}")
    proposal = result.data
    if len(json.dumps(proposal, ensure_ascii=False)) > 20000:
        raise AppError("UI_MODEL_OUTPUT_INVALID", "模型候选格式或大小不符合限制", 422)
    if candidate.candidate_type == "automation_bundle":
        try:
            proposal = UiAutomationBundle.model_validate(proposal).model_dump(mode="json")
        except ValueError as exc:
            raise AppError("UI_MODEL_OUTPUT_INVALID", "模型没有返回可确认的 UI 自动化候选包", 422) from exc
    elif candidate.candidate_type == "repair":
        try:
            proposal = UiRepairProposal.model_validate(proposal).model_dump(mode="json")
        except ValueError as exc:
            raise AppError("UI_MODEL_OUTPUT_INVALID", "模型没有返回有效的失败修复候选", 422) from exc
    candidate.model_config_id = config.id
    candidate.content = {"instruction": context["instruction"], "proposal": mask_data(proposal),
        "llm_call_id": result.call_id, "model_config_revision_id": result.model_config_revision_id,
        "safety": "候选未验证且不会自动写入资产或执行任务"}
    candidate.status = "pending_review"
    return candidate.content
