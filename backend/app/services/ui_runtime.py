from __future__ import annotations

from copy import deepcopy
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import (TestEnvironment, UiAutomationCandidate, UiElement, UiExecutionReport, UiExecutionReportStep, UiExecutionStep,
                        UiExecutionTask, UiExplorationSession, UiExplorationStep, UiPage,
                        UiModule, UiPageStep, UiPageStepDetail, UiScenario, UiScenarioStep, User)
from app.models import ModelConfig, UiExplorationTurn
from app.models.requirement_ai import RequirementCoverage, RequirementReview, RequirementTestPoint
from app.services.identity import require_membership
from app.services.masking import mask_data
from app.services.queue import enqueue_ui_actuator
from app.services.ui_assets import _one, element_view, page_view, page_step_detail_view, page_step_view, scenario_view
from app.services.ui_verification import resolve_target_url, safe_url
from app.schemas.ui import UiAutomationBundle


def _time(value):
    return value.isoformat() if value else None


def exploration_step_view(row: UiExplorationStep, include_dom: bool = False) -> dict:
    result = {
        "id": row.id, "seq": row.seq, "operation": row.operation, "locator": row.locator,
        "status": row.status, "actual_url": row.actual_url, "evidence_ref": row.evidence_ref,
        "error_code": row.error_code, "error_message": row.error_message,
        "started_at": _time(row.started_at), "finished_at": _time(row.finished_at),
    }
    if include_dom:
        result["dom_summary"] = row.dom_summary
    return result


def exploration_view(row: UiExplorationSession, steps: list[UiExplorationStep] | None = None, include_dom: bool = False,
                     turns: list[UiExplorationTurn] | None = None) -> dict:
    result = {
        "id": row.id, "project_id": row.project_id, "environment_id": row.environment_id,
        "model_config_id": row.model_config_id,
        "goal": row.goal, "requirement_test_point_ids": row.requirement_test_point_ids, "start_url": row.start_url, "allowed_paths": row.allowed_paths,
        "allowed_operations": row.allowed_operations, "blocked_operations": row.blocked_operations,
        "max_steps": row.max_steps, "total_timeout_ms": row.total_timeout_ms, "status": row.status,
        "navigation_timeout_ms": row.navigation_timeout_ms, "operation_timeout_ms": row.operation_timeout_ms,
        "llm_turn_timeout_ms": row.llm_turn_timeout_ms,
        "current_url": row.current_url, "error_code": row.error_code, "error_message": row.error_message,
        "last_evidence_ref": row.last_evidence_ref,
        "created_by": row.created_by, "created_at": _time(row.created_at), "started_at": _time(row.started_at),
        "finished_at": _time(row.finished_at),
    }
    if include_dom:
        result["dom_summary"] = row.dom_summary
    if steps is not None:
        result["steps"] = [exploration_step_view(step, include_dom) for step in steps]
    if turns is not None:
        result["turns"] = [{"id": turn.id, "seq": turn.seq, "state": turn.state,
            "action_proposal": turn.action_proposal, "policy_decision": turn.policy_decision,
            "observation": turn.observation, "approval_status": turn.approval_status,
            "llm_call_id": turn.llm_call_id, "error_code": turn.error_code, "error_message": turn.error_message,
            # Flatten the safe audit fields consumed by the failure UI while retaining the full nested record.
            "original_element_key": (turn.action_proposal or {}).get("original_target_element_key") or (turn.observation or {}).get("original_element_key"),
            "final_element_key": (turn.action_proposal or {}).get("final_target_element_key") or (turn.observation or {}).get("final_element_key"),
            "relocation": (turn.observation or {}).get("relocation", {"occurred": False}),
            "relocation_status": ((turn.observation or {}).get("relocation") or {}).get("status"),
            "relocation_failure_reason": ((turn.observation or {}).get("relocation") or {}).get("reason"),
            # Compatibility aliases keep clients on the earlier exploration diagnostics contract usable.
            "original_target_element_key": (turn.action_proposal or {}).get("original_target_element_key") or (turn.observation or {}).get("original_element_key"),
            "final_target_element_key": (turn.action_proposal or {}).get("final_target_element_key") or (turn.observation or {}).get("final_element_key"),
            "relocated": bool(((turn.observation or {}).get("relocation") or {}).get("occurred")),
            "relocation_result": ((turn.observation or {}).get("relocation") or {}).get("status"),
            "relocation_reason": ((turn.observation or {}).get("relocation") or {}).get("reason"),
            "started_at": _time(turn.started_at), "finished_at": _time(turn.finished_at),
            "revision": turn.revision} for turn in turns]
    return result


def execution_step_view(row: UiExecutionStep) -> dict:
    return {
        "id": row.id, "seq": row.seq, "name": row.name, "status": row.status,
        "action": row.action_snapshot, "result": row.result_snapshot, "evidence_refs": row.evidence_refs,
        "error_category": row.error_category, "error_message": row.error_message,
        "started_at": _time(row.started_at), "finished_at": _time(row.finished_at), "duration_ms": row.duration_ms,
    }


def execution_view(row: UiExecutionTask, steps: list[UiExecutionStep] | None = None) -> dict:
    return {
        "id": row.id, "project_id": row.project_id, "scenario_id": row.scenario_id,
        "environment_id": row.environment_id, "status": row.status, "cancel_requested": row.cancel_requested,
        "event_version": row.event_version, "error_category": row.error_category, "error_message": row.error_message,
        "created_at": _time(row.created_at), "started_at": _time(row.started_at), "finished_at": _time(row.finished_at),
        "steps": [execution_step_view(step) for step in (steps or [])],
    }


def candidate_view(row: UiAutomationCandidate) -> dict:
    return {
        "id": row.id, "project_id": row.project_id, "exploration_id": row.exploration_id,
        "execution_id": row.execution_id, "candidate_type": row.candidate_type, "status": row.status,
        "content": row.content, "source_evidence_ids": row.source_evidence_ids,
        "rejection_reason": row.rejection_reason, "confirmed_asset_id": row.confirmed_asset_id,
        "reviewed_by": row.reviewed_by, "reviewed_at": _time(row.reviewed_at),
        "created_at": _time(row.created_at),
    }


def report_view(row: UiExecutionReport, steps: list[UiExecutionReportStep] | None = None) -> dict:
    data = {"id": row.id, "execution_id": row.execution_id, "status": row.status, "summary": row.summary,
            "scenario": row.scenario_snapshot, "environment": row.environment_snapshot, "trace_manifest_ref": row.trace_manifest_ref,
            "started_at": _time(row.started_at), "finished_at": _time(row.finished_at), "created_at": _time(row.created_at)}
    if steps is not None:
        data["steps"] = [{"seq": step.seq, "name": step.name, "status": step.status, "action": step.action_snapshot,
                          "result": step.result_snapshot, "evidence_refs": step.evidence_refs, "error_category": step.error_category,
                          "error_message": step.error_message, "duration_ms": step.duration_ms} for step in steps]
    return data


async def _environment(db: AsyncSession, project_id: str, environment_id: str) -> TestEnvironment:
    row = await db.scalar(select(TestEnvironment).where(
        TestEnvironment.id == environment_id, TestEnvironment.project_id == project_id,
        TestEnvironment.is_enabled.is_(True),
    ))
    if row is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    return row


async def create_exploration(db: AsyncSession, project_id: str, user: User, data) -> dict:
    await require_membership(db, project_id, user)
    environment = await _environment(db, project_id, data.environment_id)
    start_url = await resolve_target_url(environment, "/", data.start_url)
    model_config = None
    if data.requirement_test_point_ids:
        point_ids = set(data.requirement_test_point_ids)
        points = list((await db.scalars(select(RequirementTestPoint).join(RequirementReview, RequirementReview.id == RequirementTestPoint.review_id).where(
            RequirementTestPoint.project_id == project_id, RequirementTestPoint.id.in_(point_ids),
            RequirementReview.project_id == project_id, RequirementReview.status == "approved"))).all())
        if len(points) != len(point_ids):
            raise AppError("UI_EXPLORATION_TEST_POINT_SCOPE_INVALID", "探索引用了未批准或跨项目的需求测试点", 422)
    if not data.actions:
        model_config = await db.scalar(select(ModelConfig).where(ModelConfig.is_default.is_(True), ModelConfig.is_enabled.is_(True)))
        if model_config is None or not model_config.api_key_encrypted:
            raise AppError("UI_MODEL_NOT_CONFIGURED", "AI 连续探索需要已配置的默认模型", 409)
    row = UiExplorationSession(
        project_id=project_id, environment_id=environment.id, created_by=user.id, goal=data.goal,
        requirement_test_point_ids=data.requirement_test_point_ids,
        model_config_id=model_config.id if model_config else None,
        start_url=safe_url(start_url), allowed_paths=data.allowed_paths, allowed_operations=data.allowed_operations,
        blocked_operations=data.blocked_operations, max_steps=data.max_steps,
        total_timeout_ms=data.total_timeout_ms, navigation_timeout_ms=data.navigation_timeout_ms,
        operation_timeout_ms=data.operation_timeout_ms, llm_turn_timeout_ms=data.llm_turn_timeout_ms,
        status="draft",
    )
    db.add(row)
    await db.flush()
    for seq, action in enumerate(data.actions, start=1):
        db.add(UiExplorationStep(
            project_id=project_id, exploration_id=row.id, seq=seq, operation=action.operation,
            locator=action.locator.model_dump() if action.locator else None,
            input_value={"value": action.value} if action.value else None,
        ))
    await db.commit()
    return await exploration_detail(db, project_id, user, row.id)


async def append_exploration_action(db: AsyncSession, project_id: str, user: User, exploration_id: str, data) -> dict:
    await require_membership(db, project_id, user)
    session = await _one(db, UiExplorationSession, project_id, exploration_id, "探索会话")
    if session.status != "draft":
        raise AppError("UI_EXPLORATION_NOT_EDITABLE", "探索开始后不能追加动作，请新建探索会话", 409)
    if data.action.operation not in set(session.allowed_operations) or data.action.operation in set(session.blocked_operations):
        raise AppError("UI_EXPLORATION_OPERATION_FORBIDDEN", "探索动作不在允许范围内", 422)
    count = int(await db.scalar(select(func.count()).select_from(UiExplorationStep).where(UiExplorationStep.exploration_id == session.id)) or 0)
    if count >= session.max_steps:
        raise AppError("UI_EXPLORATION_STEP_LIMIT", "探索动作已达到最大步数", 422)
    db.add(UiExplorationStep(
        project_id=project_id, exploration_id=session.id, seq=count + 1, operation=data.action.operation,
        locator=data.action.locator.model_dump() if data.action.locator else None,
        input_value={"value": data.action.value} if data.action.value else None,
    ))
    await db.commit()
    return await exploration_detail(db, project_id, user, session.id)


async def start_exploration(db: AsyncSession, project_id: str, user: User, exploration_id: str) -> dict:
    await require_membership(db, project_id, user)
    session = await _one(db, UiExplorationSession, project_id, exploration_id, "探索会话")
    if session.status != "draft":
        raise AppError("UI_EXPLORATION_NOT_STARTABLE", "只有草稿探索会话可以开始", 409)
    session.status = "pending"
    await db.commit()
    try:
        enqueue_ui_actuator("app.ui_worker_jobs.run_exploration_job", session.id, session.total_timeout_ms // 1000 + 30)
    except AppError:
        session.status = "failed"
        session.error_code = "QUEUE_UNAVAILABLE"
        session.error_message = "UI actuator 队列不可用"
        await db.commit()
        raise
    return await exploration_detail(db, project_id, user, session.id)


async def exploration_detail(db: AsyncSession, project_id: str, user: User, exploration_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await _one(db, UiExplorationSession, project_id, exploration_id, "探索会话")
    steps = list((await db.scalars(select(UiExplorationStep).where(
        UiExplorationStep.project_id == project_id, UiExplorationStep.exploration_id == row.id,
    ).order_by(UiExplorationStep.seq))).all())
    turns = list((await db.scalars(select(UiExplorationTurn).where(
        UiExplorationTurn.project_id == project_id, UiExplorationTurn.exploration_id == row.id,
    ).order_by(UiExplorationTurn.seq))).all())
    result = exploration_view(row, steps, include_dom=True, turns=turns)
    if row.model_config_id:
        config = await db.scalar(select(ModelConfig).where(ModelConfig.id == row.model_config_id))
        if config:
            result["model_name"] = config.model_name
            result["model_provider"] = config.provider
            result["model_revision"] = config.revision
    return result


async def list_explorations(db: AsyncSession, project_id: str, user: User, query) -> dict:
    await require_membership(db, project_id, user)
    stmt = select(UiExplorationSession).where(UiExplorationSession.project_id == project_id)
    if query.search:
        stmt = stmt.where(UiExplorationSession.goal.ilike(f"%{query.search.strip()}%"))
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(UiExplorationSession.created_at.desc()).offset(
        (query.page - 1) * query.page_size).limit(query.page_size))).all())
    config_ids = {row.model_config_id for row in rows if row.model_config_id}
    configs = list((await db.scalars(select(ModelConfig).where(ModelConfig.id.in_(config_ids)))).all()) if config_ids else []
    config_map = {config.id: config for config in configs}
    items = []
    for row in rows:
        item = exploration_view(row)
        config = config_map.get(row.model_config_id)
        if config:
            item.update(model_name=config.model_name, model_provider=config.provider, model_revision=config.revision)
        items.append(item)
    return {"items": items, "page": query.page, "page_size": query.page_size, "total": total}


async def cancel_exploration(db: AsyncSession, project_id: str, user: User, exploration_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await _one(db, UiExplorationSession, project_id, exploration_id, "探索会话")
    if row.status not in {"draft", "pending", "running", "waiting_approval"}:
        raise AppError("UI_EXPLORATION_NOT_CANCELABLE", "探索会话已进入终态", 409)
    row.status = "canceled"
    row.finished_at = datetime.now(UTC)
    await db.commit()
    return exploration_view(row)


async def decide_exploration_turn(db: AsyncSession, project_id: str, user: User, exploration_id: str, turn_id: str, decision: str) -> dict:
    await require_membership(db, project_id, user)
    session = await _one(db, UiExplorationSession, project_id, exploration_id, "探索会话")
    turn = await db.scalar(select(UiExplorationTurn).where(UiExplorationTurn.id == turn_id,
        UiExplorationTurn.exploration_id == session.id, UiExplorationTurn.project_id == project_id))
    if turn is None: raise AppError("RESOURCE_NOT_FOUND", "探索轮次不存在", 404)
    if session.status != "waiting_approval" or turn.approval_status != "pending":
        raise AppError("UI_EXPLORATION_APPROVAL_NOT_PENDING", "当前没有待审批动作", 409)
    turn.approval_status = decision
    if decision == "rejected":
        turn.state = "rejected"; session.status = "canceled"; session.finished_at = datetime.now(UTC)
    await db.commit()
    return {"turn_id": turn.id, "decision": decision, "session_status": session.status}


async def _scenario_snapshot(db: AsyncSession, project_id: str, scenario: UiScenario) -> dict:
    scenario_steps = list((await db.scalars(select(UiScenarioStep).where(
        UiScenarioStep.project_id == project_id, UiScenarioStep.scenario_id == scenario.id,
    ).order_by(UiScenarioStep.step_sort))).all())
    step_ids = {row.page_step_id for row in scenario_steps}
    page_steps = list((await db.scalars(select(UiPageStep).where(
        UiPageStep.project_id == project_id, UiPageStep.id.in_(step_ids),
    ))).all()) if step_ids else []
    if len(page_steps) != len(step_ids):
        raise AppError("UI_SCENARIO_SNAPSHOT_INVALID", "场景引用了已不存在的页面步骤", 409)
    details = list((await db.scalars(select(UiPageStepDetail).where(
        UiPageStepDetail.project_id == project_id, UiPageStepDetail.page_step_id.in_(step_ids),
    ).order_by(UiPageStepDetail.page_step_id, UiPageStepDetail.step_sort))).all()) if step_ids else []
    element_ids = {detail.element_id for detail in details if detail.element_id}
    elements = list((await db.scalars(select(UiElement).where(
        UiElement.project_id == project_id, UiElement.id.in_(element_ids),
    ))).all()) if element_ids else []
    if len(elements) != len(element_ids):
        raise AppError("UI_SCENARIO_SNAPSHOT_INVALID", "场景引用了已不存在的页面元素", 409)
    pages = list((await db.scalars(select(UiPage).where(
        UiPage.project_id == project_id, UiPage.id.in_({item.page_id for item in page_steps}),
    ))).all()) if page_steps else []
    by_step = {row.id: row for row in page_steps}
    by_details: dict[str, list[UiPageStepDetail]] = {item.id: [] for item in page_steps}
    for detail in details:
        by_details[detail.page_step_id].append(detail)
    by_element = {row.id: row for row in elements}
    by_page = {row.id: row for row in pages}
    return {
        "id": scenario.id, "name": scenario.name, "revision": scenario.revision, "module_id": scenario.module_id,
        "steps": [
            {
                "seq": item.step_sort, "data_override": mask_data(deepcopy(item.data_override)),
                "page_step": page_step_view(by_step[item.page_step_id], by_details[item.page_step_id]),
                "page": page_view(by_page[by_step[item.page_step_id].page_id]),
                "elements": {element_id: element_view(element) for element_id, element in by_element.items()},
            }
            for item in scenario_steps
        ],
    }


async def create_execution(db: AsyncSession, project_id: str, user: User, scenario_id: str, data, idempotency_key: str) -> tuple[dict, bool]:
    await require_membership(db, project_id, user)
    if not idempotency_key or len(idempotency_key) > 128:
        raise AppError("IDEMPOTENCY_KEY_REQUIRED", "必须提供有效 Idempotency-Key", 422)
    existing = await db.scalar(select(UiExecutionTask).where(
        UiExecutionTask.project_id == project_id, UiExecutionTask.idempotency_key == idempotency_key,
    ))
    if existing:
        return execution_view(existing), False
    scenario = await _one(db, UiScenario, project_id, scenario_id, "UI 场景")
    if scenario.status != "confirmed":
        raise AppError("UI_SCENARIO_NOT_CONFIRMED", "未确认的 UI 场景不能执行", 409)
    environment = await _environment(db, project_id, data.environment_id)
    snapshot = await _scenario_snapshot(db, project_id, scenario)
    row = UiExecutionTask(
        project_id=project_id, scenario_id=scenario.id, environment_id=environment.id,
        idempotency_key=idempotency_key, scenario_snapshot=snapshot,
        environment_snapshot=mask_data({"id": environment.id, "name": environment.name, "base_url": environment.base_url,
                                        "variables": environment.variables, "secret_refs": environment.secret_refs,
                                        "revision": environment.revision}), created_by=user.id,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(UiExecutionTask).where(
            UiExecutionTask.project_id == project_id, UiExecutionTask.idempotency_key == idempotency_key,
        ))
        return execution_view(existing), False
    try:
        enqueue_ui_actuator("app.ui_worker_jobs.run_ui_execution_job", row.id, 900)
    except AppError:
        row.status = "failed"
        row.error_category = "queue_unavailable"
        row.error_message = "UI actuator 队列不可用"
        row.finished_at = datetime.now(UTC)
        await db.commit()
        raise
    return execution_view(row), True


async def execution_detail(db: AsyncSession, project_id: str, user: User, execution_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await _one(db, UiExecutionTask, project_id, execution_id, "UI 执行任务")
    steps = list((await db.scalars(select(UiExecutionStep).where(
        UiExecutionStep.project_id == project_id, UiExecutionStep.execution_id == row.id,
    ).order_by(UiExecutionStep.seq))).all())
    return execution_view(row, steps)


async def list_executions(db: AsyncSession, project_id: str, user: User, query) -> dict:
    await require_membership(db, project_id, user)
    stmt = select(UiExecutionTask).where(UiExecutionTask.project_id == project_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(UiExecutionTask.created_at.desc()).offset(
        (query.page - 1) * query.page_size).limit(query.page_size))).all())
    return {"items": [execution_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def cancel_execution(db: AsyncSession, project_id: str, user: User, execution_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await _one(db, UiExecutionTask, project_id, execution_id, "UI 执行任务")
    if row.status not in {"pending", "running"}:
        raise AppError("UI_EXECUTION_NOT_CANCELABLE", "UI 执行任务已进入终态", 409)
    row.cancel_requested = True
    row.event_version += 1
    await db.commit()
    return execution_view(row)


async def list_reports(db: AsyncSession, project_id: str, user: User, query) -> dict:
    await require_membership(db, project_id, user)
    stmt = select(UiExecutionReport).where(UiExecutionReport.project_id == project_id)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(UiExecutionReport.created_at.desc()).offset(
        (query.page - 1) * query.page_size).limit(query.page_size))).all())
    return {"items": [report_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def report_detail(db: AsyncSession, project_id: str, user: User, report_id: str) -> dict:
    await require_membership(db, project_id, user)
    report = await _one(db, UiExecutionReport, project_id, report_id, "UI 执行报告")
    steps = list((await db.scalars(select(UiExecutionReportStep).where(
        UiExecutionReportStep.project_id == project_id, UiExecutionReportStep.report_id == report.id,
    ).order_by(UiExecutionReportStep.seq))).all())
    return report_view(report, steps)


async def list_candidates(db: AsyncSession, project_id: str, user: User, query, status: str | None = None) -> dict:
    await require_membership(db, project_id, user)
    stmt = select(UiAutomationCandidate).where(UiAutomationCandidate.project_id == project_id)
    if status:
        stmt = stmt.where(UiAutomationCandidate.status == status)
    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list((await db.scalars(stmt.order_by(UiAutomationCandidate.created_at.desc()).offset(
        (query.page - 1) * query.page_size).limit(query.page_size))).all())
    return {"items": [candidate_view(row) for row in rows], "page": query.page, "page_size": query.page_size, "total": total}


async def request_candidate(db: AsyncSession, project_id: str, user: User, data) -> dict:
    await require_membership(db, project_id, user)
    if data.exploration_id:
        await _one(db, UiExplorationSession, project_id, data.exploration_id, "探索会话")
    if data.execution_id:
        await _one(db, UiExecutionTask, project_id, data.execution_id, "UI 执行任务")
    row = UiAutomationCandidate(project_id=project_id, exploration_id=data.exploration_id, execution_id=data.execution_id,
                                candidate_type=data.candidate_type, status="generating", content={"instruction": data.instruction}, created_by=user.id)
    db.add(row)
    await db.commit()
    enqueue_ui_actuator("app.ui_worker_jobs.generate_ui_candidate_job", row.id, 180)
    return candidate_view(row)


async def review_candidate(db: AsyncSession, project_id: str, user: User, candidate_id: str, data) -> dict:
    await require_membership(db, project_id, user)
    row = await _one(db, UiAutomationCandidate, project_id, candidate_id, "UI 候选")
    if row.status != "pending_review":
        raise AppError("UI_CANDIDATE_NOT_REVIEWABLE", "候选尚未生成完成或已审核", 409)
    row.status = data.decision
    row.reviewed_by = user.id
    row.reviewed_at = datetime.now(UTC)
    row.rejection_reason = data.reason if data.decision == "rejected" else None
    await db.commit()
    return candidate_view(row)


async def confirm_candidate_bundle(db: AsyncSession, project_id: str, user: User, candidate_id: str) -> dict:
    """Materialize an explicitly approved proposal as one project-scoped test flow.

    The candidate is not trusted merely because it came from a model: Pydantic has
    already checked its graph, and this service validates the exploration scope
    again before persisting anything. A failure rolls back the whole bundle.
    """
    await require_membership(db, project_id, user)
    candidate = await _one(db, UiAutomationCandidate, project_id, candidate_id, "UI 候选")
    if candidate.candidate_type != "automation_bundle":
        raise AppError("UI_CANDIDATE_TYPE_INVALID", "只有自动化候选包可以确认创建测试流程", 422)
    if candidate.status == "superseded":
        if candidate.confirmed_asset_id:
            return {"scenario": await _scenario_for_confirmation(db, project_id, candidate.confirmed_asset_id), "candidate": candidate_view(candidate), "created": False}
        raise AppError("UI_CANDIDATE_CONFIRMATION_INVALID", "候选确认状态不完整", 409)
    if candidate.status != "approved":
        raise AppError("UI_CANDIDATE_NOT_CONFIRMABLE", "候选必须先通过人工审核", 409)
    if not candidate.exploration_id:
        raise AppError("UI_CANDIDATE_SOURCE_REQUIRED", "自动化候选包必须来自受控探索", 422)
    try:
        bundle = UiAutomationBundle.model_validate((candidate.content or {}).get("proposal"))
    except ValueError as exc:
        raise AppError("UI_CANDIDATE_CONTENT_INVALID", "候选包内容无效，不能确认", 409) from exc
    exploration = await _one(db, UiExplorationSession, project_id, candidate.exploration_id, "探索会话")
    if exploration.status != "completed":
        raise AppError("UI_EXPLORATION_NOT_COMPLETED", "探索完成后才能确认测试流程", 409)
    environment = await _environment(db, project_id, exploration.environment_id)

    test_point_ids = set(bundle.requirement_test_point_ids)
    if test_point_ids:
        test_points = list((await db.scalars(select(RequirementTestPoint).join(
            RequirementReview, RequirementReview.id == RequirementTestPoint.review_id).where(
            RequirementTestPoint.project_id == project_id, RequirementTestPoint.id.in_(test_point_ids),
            RequirementReview.project_id == project_id, RequirementReview.status == "approved"))).all())
        if len(test_points) != len(test_point_ids):
            raise AppError("UI_BUNDLE_TEST_POINT_SCOPE_INVALID", "候选引用了未批准或跨项目的需求测试点", 422)

    try:
        inventory = json.loads(exploration.dom_summary or "[]")
    except ValueError:
        inventory = []
    allowed_locators = {json.dumps(locator, sort_keys=True) for item in inventory for locator in item.get("locator_candidates", [])}
    for element in bundle.elements:
        requested = [element.primary_locator, *element.fallback_locators]
        if any(json.dumps(locator.model_dump(exclude_none=True), sort_keys=True) not in allowed_locators for locator in requested):
            raise AppError("UI_BUNDLE_LOCATOR_NOT_COLLECTED", "候选 Locator 不属于探索采集结果", 422)

    def allowed(url: str) -> bool:
        from urllib.parse import urlsplit
        path = urlsplit(url).path or "/"
        return not exploration.allowed_paths or any(path == item or path.startswith(item.rstrip("/") + "/") for item in exploration.allowed_paths)

    for page in bundle.pages:
        target = await resolve_target_url(environment, "/", page.url)
        if not allowed(target):
            raise AppError("UI_BUNDLE_PAGE_SCOPE_INVALID", "候选页面超出探索允许范围", 422)

    try:
        module = UiModule(project_id=project_id, name=bundle.module_name, description=bundle.module_description, created_by=user.id)
        db.add(module)
        await db.flush()
        pages: dict[str, UiPage] = {}
        for source in bundle.pages:
            page = UiPage(project_id=project_id, module_id=module.id, name=source.name, url=source.url, description=source.description, created_by=user.id)
            db.add(page)
            pages[source.key] = page
        await db.flush()
        elements: dict[str, UiElement] = {}
        for source in bundle.elements:
            element = UiElement(
                project_id=project_id, page_id=pages[source.page_key].id, name=source.name,
                primary_locator=source.primary_locator.model_dump(),
                fallback_locators=[item.model_dump() for item in source.fallback_locators],
                iframe_locator=source.iframe_locator.model_dump() if source.iframe_locator else None,
                description=source.description, created_by=user.id,
            )
            db.add(element)
            elements[source.key] = element
        await db.flush()
        page_steps: dict[str, UiPageStep] = {}
        for source in bundle.page_steps:
            page_step = UiPageStep(project_id=project_id, page_id=pages[source.page_key].id, module_id=module.id, name=source.name, description=source.description, created_by=user.id)
            db.add(page_step)
            page_steps[source.key] = page_step
        await db.flush()
        for source in bundle.page_steps:
            for detail in source.details:
                db.add(UiPageStepDetail(
                    project_id=project_id, page_step_id=page_steps[source.key].id, step_sort=detail.step_sort,
                    step_type=detail.step_type, element_id=elements[detail.element_key].id if detail.element_key else None,
                    operation=detail.operation, input_value=mask_data(deepcopy(detail.input_value)) if detail.input_value else None,
                    assertion=mask_data(deepcopy(detail.assertion)), description=detail.description,
                ))
        scenario = UiScenario(
            project_id=project_id, module_id=module.id, name=bundle.scenario_name, description=bundle.scenario_description,
            status="draft", confirmed_at=None, created_by=user.id,
        )
        db.add(scenario)
        await db.flush()
        for seq, key in enumerate(bundle.scenario_step_keys, start=1):
            db.add(UiScenarioStep(project_id=project_id, scenario_id=scenario.id, page_step_id=page_steps[key].id, step_sort=seq, data_override={}))
        for test_point_id in test_point_ids:
            db.add(RequirementCoverage(project_id=project_id, test_point_id=test_point_id, scenario_type="ui",
                scenario_id=scenario.id, status="CANDIDATE", created_by=user.id))
        candidate.status = "superseded"
        candidate.confirmed_asset_id = scenario.id
        candidate.reviewed_by = user.id
        candidate.reviewed_at = datetime.now(UTC)
        candidate.content = {**candidate.content, "confirmed_bundle": {"module_id": module.id, "scenario_id": scenario.id}}
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AppError("UI_BUNDLE_ASSET_EXISTS", "候选与现有 UI 资产名称冲突，请编辑候选后确认", 409) from exc
    return {"scenario": await _scenario_for_confirmation(db, project_id, scenario.id), "candidate": candidate_view(candidate), "created": True}


async def _scenario_for_confirmation(db: AsyncSession, project_id: str, scenario_id: str) -> dict:
    scenario = await _one(db, UiScenario, project_id, scenario_id, "UI 场景")
    steps = list((await db.scalars(select(UiScenarioStep).where(
        UiScenarioStep.project_id == project_id, UiScenarioStep.scenario_id == scenario.id,
    ).order_by(UiScenarioStep.step_sort))).all())
    return scenario_view(scenario, steps)
