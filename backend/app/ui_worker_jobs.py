from __future__ import annotations

import asyncio
import re
import hashlib
import json
import os
import secrets
import time
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from sqlalchemy import select

from app.config import get_settings
from app.database import worker_db_session
from app.models import (UiAutomationCandidate, UiEvidence, UiExecutionReport, UiExecutionReportStep,
                        UiExecutionStep, UiExecutionTask, UiExplorationSession, UiExplorationStep)
from app.security import decrypt_secret
from app.models import UiExplorationTurn
from app.models.requirement_ai import RequirementCoverage
from app.schemas.ui import UiAiAction
from app.services.events import publish_ui_execution
from app.services.masking import mask_data
from app.services.queue import enqueue_ui_actuator
from app.services.ui_ai import generate_candidate
from app.services.llm import DefaultLlmGateway
from app.services.ui_collection import locator_candidates
from app.services.ui_policy import check_action
from app.services.ui_verification import _frame_root, _locator, _origin, mask_sensitive_text, safe_url

LEASE_SECONDS = 45
MAX_EVIDENCE_BYTES = 5 * 1024 * 1024
MASK_STYLE = """
body * { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; }
input[type=password], input[autocomplete*=password], [data-sensitive],
input[name*=token i], input[name*=secret i], input[name*=email i], input[name*=phone i],
textarea[name*=token i], textarea[name*=secret i] { color: transparent !important; -webkit-text-security: disc !important; }
img, video, canvas { filter: blur(24px) !important; }
"""


class ExplorationStageTimeout(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _remaining_timeout_ms(deadline: float, configured_timeout_ms: int, stage: str) -> int:
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise ExplorationStageTimeout("UI_EXPLORATION_TIMEOUT", "探索会话总超时")
    return min(configured_timeout_ms, remaining)


def run_exploration_job(exploration_id: str) -> None:
    asyncio.run(_run_exploration(exploration_id))


def run_ui_execution_job(execution_id: str) -> None:
    asyncio.run(_run_execution(execution_id))


async def _dom_inventory(page) -> str:
    """Collect a bounded, redacted element inventory using only a static script."""
    inventory = await page.locator("button, input, textarea, select, a, [role], [data-testid]").evaluate_all(
        """nodes => nodes.slice(0, 160).map((node, index) => ({
          index,
          tag: node.tagName.toLowerCase(),
          role: node.getAttribute('role'),
          test_id: node.getAttribute('data-testid') || node.getAttribute('data-test-id'),
          id: node.id || null,
          name: node.getAttribute('name'),
          label: node.getAttribute('aria-label'),
          placeholder: node.getAttribute('placeholder'),
          text: (node.innerText || node.getAttribute('value') || '').slice(0, 120),
          disabled: !!node.disabled
        }))""",
    )
    for item in inventory:
        if item.get("tag") == "input" and str(item.get("name") or "").lower().find("password") >= 0:
            item["text"] = "[REDACTED]"
    return mask_sensitive_text(json.dumps(inventory, ensure_ascii=False, separators=(",", ":")))[:30000]


async def _record_evidence(db, project_id: str, owner_type: str, owner_id: str, kind: str, payload: bytes, suffix: str, created_by: str) -> str:
    if suffix not in {"png", "txt", "json"} or len(payload) > MAX_EVIDENCE_BYTES:
        raise RuntimeError("UI_EVIDENCE_REJECTED")
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"ui-evidence/{project_id}/{owner_type}/{owner_id}/{time.time_ns()}-{digest[:12]}.{suffix}"
    path = get_settings().upload_root / object_key
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_bytes, payload)
    row = UiEvidence(project_id=project_id, owner_type=owner_type, owner_id=owner_id, kind=kind, object_key=object_key,
                     content_type={"png": "image/png", "txt": "text/plain; charset=utf-8", "json": "application/json"}[suffix], byte_size=len(payload),
                     sha256=digest, created_by=created_by)
    db.add(row)
    await db.flush()
    return row.id


async def _mask_screenshot(page) -> bytes:
    await page.add_style_tag(content=MASK_STYLE)
    return await page.screenshot(full_page=False)


def _assert_allowed_url(url: str, origin: tuple[str, str, int], allowed_paths: list[str]) -> None:
    parts = urlsplit(url)
    if _origin(url) != origin:
        raise RuntimeError("UI_REDIRECT_FORBIDDEN")
    paths = allowed_paths or [parts.path]
    if not any(parts.path.startswith(prefix) for prefix in paths):
        raise RuntimeError("UI_PATH_FORBIDDEN")


def _exploration_error_code(exc: Exception) -> str:
    """Map browser failures to actionable, non-sensitive categories."""
    value = str(exc).upper()
    name = type(exc).__name__.upper()
    if isinstance(exc, ExplorationStageTimeout):
        return exc.code
    if "UI_REDIRECT_FORBIDDEN" in value:
        return "UI_REDIRECT_FORBIDDEN"
    if "UI_PATH_FORBIDDEN" in value:
        return "UI_PATH_FORBIDDEN"
    if "UNEXPECTED KEYWORD ARGUMENT" in value or "TYPEERROR" in name:
        return "ACTUATOR_COMPATIBILITY_ERROR"
    for llm_code in ("LLM_TIMEOUT", "LLM_AUTH_FAILED", "LLM_RATE_LIMITED", "LLM_NETWORK_ERROR", "LLM_RESPONSE_JSON_INVALID", "LLM_RESPONSE_SCHEMA_INVALID", "LLM_UPSTREAM_ERROR"):
        if llm_code in value:
            return "LLM_GATEWAY_TIMEOUT" if llm_code == "LLM_TIMEOUT" else llm_code
    if "MODEL" in value and "504" in value:
        return "LLM_GATEWAY_TIMEOUT"
    if "OPERATION_TIMEOUT" in value:
        return "BROWSER_OPERATION_TIMEOUT"
    if "NAVIGATION_TIMEOUT" in value:
        return "PAGE_NAVIGATION_TIMEOUT"
    if "TIMEOUT" in name or "TIMEOUT" in value:
        return "PAGE_NAVIGATION_TIMEOUT"
    if any(item in value for item in ("ERR_NAME_NOT_RESOLVED", "ENOTFOUND", "DNS")):
        return "PAGE_DNS_ERROR"
    if any(item in value for item in ("ERR_CONNECTION_REFUSED", "ECONNREFUSED", "CONNECTION REFUSED")):
        return "PAGE_CONNECTION_REFUSED"
    if any(item in value for item in ("CERTIFICATE", "SSL", "TLS")):
        return "PAGE_CERTIFICATE_ERROR"
    if "LAUNCH" in value or "EXECUTABLE" in value or "BROWSER" in name:
        return "BROWSER_LAUNCH_ERROR"
    if "PLAYWRIGHT" in name or "TARGET CLOSED" in value or "BROWSER" in value:
        return "BROWSER_RUNTIME_ERROR"
    return "EXPLORATION_BROWSER_ERROR"


async def _run_action(page, action: dict, origin: tuple[str, str, int], allowed_paths: list[str], *,
                      navigation_timeout_ms: int = 30000, operation_timeout_ms: int = 8000) -> dict:
    operation = action["operation"]
    timeout = min(int(action.get("timeout_ms") or operation_timeout_ms), operation_timeout_ms)
    if operation == "navigate":
        target = urljoin(page.url, str(action.get("value") or ""))
        _assert_allowed_url(target, origin, allowed_paths)
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=min(timeout, navigation_timeout_ms))
        except Exception as exc:
            if "TIMEOUT" in str(exc).upper() or "TIMEOUT" in type(exc).__name__.upper():
                raise ExplorationStageTimeout("PAGE_NAVIGATION_TIMEOUT", "页面加载超时") from exc
            raise
        _assert_allowed_url(page.url, origin, allowed_paths)
        return {"actual_url": safe_url(page.url)}
    if operation == "wait_for":
        await page.wait_for_timeout(min(timeout, 10000))
        return {"actual_url": safe_url(page.url)}
    if operation == "assert_url":
        if str(action.get("value") or "") not in page.url:
            raise RuntimeError("UI_ASSERTION_FAILED")
        return {"actual_url": safe_url(page.url)}
    root = await _frame_root(page, action.get("iframe_locator"))
    locators = action.get("locators") or [action.get("locator")]
    target = None
    locator_used = None
    last_count = 0
    try:
        for locator in [item for item in locators if item]:
            current = _locator(root, locator)
            last_count = await current.count()
            if last_count == 1 and await current.is_visible(timeout=timeout):
                target, locator_used = current, locator
                break
    except Exception as exc:
        if "TIMEOUT" in str(exc).upper() or "TIMEOUT" in type(exc).__name__.upper():
            raise ExplorationStageTimeout("BROWSER_OPERATION_TIMEOUT", "浏览器定位超时") from exc
        raise
    if target is None:
        raise RuntimeError("UI_LOCATOR_NOT_UNIQUE" if last_count > 1 else "UI_LOCATOR_NOT_FOUND")
    count = 1
    try:
        if operation == "click":
            await target.click(timeout=timeout)
        elif operation == "fill":
            value = str(action.get("value") or "")
            if value.startswith("secret://"):
                secret_name = value.removeprefix("secret://")
                if not secret_name or not all(char.isalnum() or char in "_-" for char in secret_name):
                    raise RuntimeError("UI_SECRET_REFERENCE_INVALID")
                value = os.getenv(f"AITEST_SECRET_{secret_name.upper().replace('-', '_')}", "")
                if not value:
                    raise RuntimeError("UI_SECRET_UNRESOLVED")
            await target.fill(value, timeout=timeout)
        elif operation == "select":
            await target.select_option(str(action.get("value") or ""), timeout=timeout)
        elif operation == "hover":
            await target.hover(timeout=timeout)
        elif operation == "press":
            await target.press(str(action.get("value") or "Enter"), timeout=timeout)
        elif operation == "check":
            await target.check(timeout=timeout)
        elif operation == "uncheck":
            await target.uncheck(timeout=timeout)
        elif operation == "assert_visible":
            if not await target.is_visible(timeout=timeout):
                raise RuntimeError("UI_ASSERTION_FAILED")
        elif operation == "assert_text":
            if str(action.get("value") or "") not in await target.inner_text(timeout=timeout):
                raise RuntimeError("UI_ASSERTION_FAILED")
        else:
            raise RuntimeError("UI_OPERATION_FORBIDDEN")
    except ExplorationStageTimeout:
        raise
    except Exception as exc:
        if "TIMEOUT" in str(exc).upper() or "TIMEOUT" in type(exc).__name__.upper():
            raise ExplorationStageTimeout("BROWSER_OPERATION_TIMEOUT", "浏览器操作超时") from exc
        raise
    _assert_allowed_url(page.url, origin, allowed_paths)
    return {"actual_url": safe_url(page.url), "match_count": count, "visible": await target.is_visible(timeout=timeout),
            "locator_used": locator_used}


def _failure_category(code: str) -> str:
    value = code.upper()
    if "LOCATOR" in value or "IFRAME" in value: return "LOCATOR_BROKEN"
    if "AUTH" in value or "SECRET_UNRESOLVED" in value: return "AUTH_FAILED"
    if "DATA" in value or "SECRET_REFERENCE" in value: return "TEST_DATA_ERROR"
    if "TIMEOUT" in value or "REDIRECT" in value or "PATH_FORBIDDEN" in value: return "PAGE_LOAD_ERROR"
    if "ASSERT" in value: return "EXPECTATION_MISMATCH"
    if "BROWSER" in value or "PLAYWRIGHT" in value: return "ACTUATOR_ERROR"
    return "PRODUCT_DEFECT"


async def _open_browser():
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("UI_PLAYWRIGHT_UNAVAILABLE") from exc
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=False)
    return playwright, browser, context


async def _capture_exploration_state(db, session, page, *, turn=None) -> dict:
    """Persist the latest safe DOM and screenshot before a failure can hide it."""
    observation = {"actual_url": safe_url(page.url)}
    try:
        dom_summary = await _dom_inventory(page)
        session.dom_summary = dom_summary
        observation["dom_summary"] = dom_summary
        dom_ref = await _record_evidence(db, session.project_id, "exploration_turn" if turn else "exploration_session",
                                         turn.id if turn else session.id, "dom", dom_summary.encode(), "json", session.created_by)
        observation["dom_evidence_ref"] = dom_ref
    except Exception:
        observation["dom_capture"] = "unavailable"
    try:
        png = await _mask_screenshot(page)
        screenshot_ref = await _record_evidence(db, session.project_id, "exploration_turn" if turn else "exploration_session",
                                                turn.id if turn else session.id, "screenshot", png, "png", session.created_by)
        observation["screenshot_evidence_ref"] = screenshot_ref
        session.last_evidence_ref = screenshot_ref
    except Exception:
        observation["screenshot_capture"] = "unavailable"
    session.current_url = safe_url(page.url)
    if turn is not None:
        turn.observation = {**(turn.observation or {}), **observation}
    return observation


async def _run_ai_turns(db, session, page, origin, deadline: float) -> None:
    history = []
    for seq in range(1, session.max_steps + 1):
        await db.refresh(session)
        if session.status == "canceled":
            return
        raw = json.loads(await _dom_inventory(page))
        inventory = []
        for item in raw:
            attributes = {"test_id": item.get("test_id"), "id": item.get("id"), "name": item.get("name"),
                          "label": item.get("label"), "placeholder": item.get("placeholder"), "text": item.get("text", "")}
            element = {"element_key": f"f0_{item['index']}", "tag": item.get("tag", "*"), "role": item.get("role"),
                       "accessible_name": item.get("label") or item.get("text") or item.get("placeholder") or "",
                       "attributes": attributes, "visible": True, "enabled": not item.get("disabled"),
                       "actionable": not item.get("disabled"), "frame_path": []}
            element["locator_candidates"] = locator_candidates(element)
            inventory.append(element)
        turn = UiExplorationTurn(project_id=session.project_id, exploration_id=session.id, seq=seq,
                                 state="planning", started_at=datetime.now(UTC), created_by=session.created_by)
        db.add(turn)
        await db.commit()
        try:
            # Keep model context bounded: large pages can otherwise spend the whole turn on input processing.
            prompt = mask_sensitive_text(json.dumps({"goal": session.goal, "current_url": safe_url(page.url),
                "inventory": inventory[:80], "history": history[-5:], "remaining_steps": session.max_steps - seq + 1}, ensure_ascii=False))
            await _capture_exploration_state(db, session, page, turn=turn)
            llm_timeout_ms = _remaining_timeout_ms(deadline, session.llm_turn_timeout_ms, "llm")
            llm_result = await DefaultLlmGateway(db).generate(project_id=session.project_id,
                model_config_id=session.model_config_id, prompt=prompt, response_schema=UiAiAction.model_json_schema(),
                timeout_ms=llm_timeout_ms, created_by=session.created_by, purpose="ui_exploration_turn")
            proposal = UiAiAction.model_validate(llm_result.data).model_dump()
            turn.state, turn.action_proposal, turn.llm_call_id = "action_proposed", mask_data(deepcopy(proposal)), llm_result.call_id
            target = next((item for item in inventory if item["element_key"] == proposal.get("target_element_key")), None)
            decision = check_action(action=proposal, current_url=page.url,
                element_keys={item["element_key"] for item in inventory}, allowed_operations=set(session.allowed_operations),
                blocked_operations=set(session.blocked_operations), allowed_paths=session.allowed_paths,
                element_label=(target or {}).get("accessible_name", ""))
            turn.state, turn.policy_decision = "policy_checked", decision
            await db.commit()
            if decision["requires_approval"]:
                turn.approval_status, turn.state, session.status = "pending", "waiting_approval", "waiting_approval"
                await db.commit()
                while turn.approval_status == "pending" and session.status != "canceled":
                    await asyncio.sleep(0.5)
                    await db.refresh(turn)
                    await db.refresh(session)
                if turn.approval_status != "approved":
                    return
                session.status = "running"
            action = {"operation": proposal["operation"], "value": proposal.get("value")}
            if proposal["operation"] in {"click", "fill", "select", "hover", "press", "check", "uncheck", "assert_visible", "assert_text"}:
                if not target or not target["locator_candidates"]:
                    raise RuntimeError("UI_LOCATOR_CANDIDATE_MISSING")
                action["locator"] = target["locator_candidates"][0]
            turn.state = "executing"
            await db.commit()
            action_timeout_ms = _remaining_timeout_ms(deadline, session.operation_timeout_ms, "operation")
            execution_result = await _run_action(page, action, origin, session.allowed_paths,
                navigation_timeout_ms=_remaining_timeout_ms(deadline, session.navigation_timeout_ms, "navigation"),
                operation_timeout_ms=action_timeout_ms)
            observation = {"actual_url": execution_result.get("actual_url"), "expected": proposal["expected"]}
            turn.state, turn.observation = "observation_saved", observation
            await _capture_exploration_state(db, session, page, turn=turn)
            history.append({"action": mask_data(proposal), "observation": turn.observation})
            session.heartbeat_at = datetime.now(UTC)
            session.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        except Exception as exc:
            turn.state, turn.error_code = "failed", _exploration_error_code(exc)
            turn.error_message = f"{turn.error_code}: {str(exc)[:160]}"
            await _capture_exploration_state(db, session, page, turn=turn)
            raise
        finally:
            turn.finished_at = datetime.now(UTC)
            await db.commit()


async def _run_exploration(exploration_id: str) -> None:
    async with worker_db_session() as db:
        session = await db.get(UiExplorationSession, exploration_id)
        if not session or session.status != "pending":
            return
        token = secrets.token_hex(16)
        session.status = "running"
        session.lease_token = token
        session.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        session.heartbeat_at = session.started_at = datetime.now(UTC)
        await db.commit()
        settings = get_settings()
        playwright = browser = context = page = None
        deadline = time.monotonic() + session.total_timeout_ms / 1000
        try:
            async with asyncio.timeout(session.total_timeout_ms / 1000):
                playwright, browser, context = await _open_browser()
                origin = _origin(session.start_url)
                async def route_handler(route):
                    if _origin(route.request.url) != origin:
                        await route.abort("blockedbyclient")
                    else:
                        await route.continue_()
                await context.route("**/*", route_handler)
                await context.tracing.start(screenshots=True, snapshots=True, sources=False)
                page = await context.new_page()
                page.set_default_timeout(session.operation_timeout_ms)
                page.set_default_navigation_timeout(session.navigation_timeout_ms)
                try:
                    await page.goto(session.start_url, wait_until="domcontentloaded",
                                    timeout=_remaining_timeout_ms(deadline, session.navigation_timeout_ms, "navigation"))
                except Exception as exc:
                    if "TIMEOUT" in str(exc).upper() or "TIMEOUT" in type(exc).__name__.upper():
                        raise ExplorationStageTimeout("PAGE_NAVIGATION_TIMEOUT", "起始页面加载超时") from exc
                    raise
                _assert_allowed_url(page.url, origin, session.allowed_paths)
                steps = list((await db.scalars(select(UiExplorationStep).where(UiExplorationStep.exploration_id == session.id).order_by(UiExplorationStep.seq))).all())
                if not steps and session.model_config_id:
                    await _run_ai_turns(db, session, page, origin, deadline)
                for step in steps:
                    await db.refresh(session)
                    if session.status == "canceled":
                        break
                    if step.operation not in set(session.allowed_operations) or step.operation in set(session.blocked_operations):
                        step.status, step.error_code, step.finished_at = "failed", "UI_EXPLORATION_OPERATION_FORBIDDEN", datetime.now(UTC)
                        continue
                    step.status, step.started_at = "running", datetime.now(UTC)
                    action = {"operation": step.operation, "locator": step.locator, "value": (step.input_value or {}).get("value")}
                    try:
                        result = await _run_action(page, action, origin, session.allowed_paths,
                            navigation_timeout_ms=_remaining_timeout_ms(deadline, session.navigation_timeout_ms, "navigation"),
                            operation_timeout_ms=_remaining_timeout_ms(deadline, session.operation_timeout_ms, "operation"))
                        step.status, step.actual_url = "passed", result.get("actual_url")
                    except Exception as exc:
                        step.status, step.error_code = "failed", _exploration_error_code(exc)
                        step.error_message = f"{step.error_code}: 受控探索动作未完成"
                        step.finished_at = datetime.now(UTC)
                        await _capture_exploration_state(db, session, page)
                        session.error_code = step.error_code
                        session.error_message = step.error_message
                        break
                    step.dom_summary = await _dom_inventory(page)
                    png = await _mask_screenshot(page)
                    evidence_id = await _record_evidence(db, session.project_id, "exploration_step", step.id, "screenshot", png, "png", session.created_by)
                    step.evidence_ref = evidence_id
                    step.finished_at = datetime.now(UTC)
                    session.current_url = step.actual_url
                    session.dom_summary = step.dom_summary
                    session.heartbeat_at = datetime.now(UTC)
                    session.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
                    await db.commit()
                if session.status not in {"canceled", "waiting_approval"}:
                    session.status = "failed" if session.error_code else "completed"
                    session.current_url = safe_url(page.url)
                    if steps:
                        session.dom_summary = await _dom_inventory(page)
                trace = get_settings().upload_root / f"tmp-{session.id}.zip"
                await context.tracing.stop(path=str(trace))
                if trace.exists():
                    # Trace is binary and can contain rendered page content. Do not retain it until an approved redaction pipeline exists.
                    trace.unlink(missing_ok=True)
        except TimeoutError:
            session.status, session.error_code, session.error_message = "failed", "UI_EXPLORATION_TIMEOUT", "探索会话总超时"
        except Exception as exc:
            # Keep diagnostics useful while preventing credentials and query data from entering logs/UI.
            raw = f"{type(exc).__name__}: {exc}"
            redacted = re.sub(r"(?i)(authorization|cookie|token|password|passwd|api[_-]?key)=([^\s&;]+)", r"\1=[REDACTED]", raw)
            redacted = re.sub(r"https?://[^\s]+", lambda m: m.group(0).split("?", 1)[0], redacted)
            redacted = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", redacted)
            code = _exploration_error_code(exc)
            session.status, session.error_code = "failed", code
            session.error_message = f"{code}: {redacted[:240]}"
        finally:
            if page is not None and session.status == "failed":
                await _capture_exploration_state(db, session, page)
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()
            if playwright is not None:
                await playwright.stop()
            session.finished_at = datetime.now(UTC)
            session.lease_token = None
            session.lease_expires_at = None
            await db.commit()
            if session.status == "completed":
                candidate = UiAutomationCandidate(
                    project_id=session.project_id, exploration_id=session.id, candidate_type="automation_bundle",
                    status="generating", content={"instruction": session.goal}, created_by=session.created_by,
                )
                db.add(candidate)
                await db.commit()
                try:
                    enqueue_ui_actuator("app.ui_worker_jobs.generate_ui_candidate_job", candidate.id, 180)
                except Exception:
                    candidate.status = "failed"
                    candidate.content = {"error_code": "QUEUE_UNAVAILABLE", "message": "AI 候选队列不可用，未写入任何资产"}
                    await db.commit()


async def _emit(db, task: UiExecutionTask, event_type: str, data: dict) -> None:
    task.event_version += 1
    await db.commit()
    publish_ui_execution(task.id, {"type": event_type, "version": task.event_version, "data": data})


async def _ensure_ui_report(db, task: UiExecutionTask) -> None:
    existing = await db.scalar(select(UiExecutionReport).where(UiExecutionReport.execution_id == task.id))
    if existing:
        return existing
    steps = list((await db.scalars(select(UiExecutionStep).where(UiExecutionStep.execution_id == task.id).order_by(UiExecutionStep.seq))).all())
    counts = {status: sum(step.status == status for step in steps) for status in ("passed", "failed", "error", "skipped", "canceled")}
    report = UiExecutionReport(project_id=task.project_id, execution_id=task.id,
        status="passed" if task.status == "completed" else task.status,
        summary={**counts, "total": len(steps), "duration_ms": sum(step.duration_ms for step in steps)},
        scenario_snapshot=deepcopy(task.scenario_snapshot), environment_snapshot=deepcopy(task.environment_snapshot),
        trace_manifest_ref=task.trace_manifest_ref,
        triggered_by=task.created_by, started_at=task.started_at, finished_at=task.finished_at)
    db.add(report)
    await db.flush()
    for step in steps:
        db.add(UiExecutionReportStep(project_id=task.project_id, report_id=report.id, seq=step.seq, name=step.name,
            status=step.status, action_snapshot=deepcopy(step.action_snapshot), result_snapshot=deepcopy(step.result_snapshot),
            evidence_refs=list(step.evidence_refs), error_category=step.error_category, error_message=step.error_message,
            duration_ms=step.duration_ms))
    coverages = list((await db.scalars(select(RequirementCoverage).where(
        RequirementCoverage.project_id == task.project_id, RequirementCoverage.scenario_type == "ui",
        RequirementCoverage.scenario_id == task.scenario_id))).all())
    for coverage in coverages:
        coverage.status = "PASSED" if task.status == "completed" else "FAILED"
        coverage.execution_report_id = report.id
        coverage.revision += 1
    await db.commit()
    return report


async def _run_execution(execution_id: str) -> None:
    async with worker_db_session() as db:
        task = await db.get(UiExecutionTask, execution_id)
        if not task or task.status != "pending":
            return
        task.status, task.started_at, task.heartbeat_at = "running", datetime.now(UTC), datetime.now(UTC)
        task.lease_token = secrets.token_hex(16)
        task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        await _emit(db, task, "execution_update", {"status": "running"})
        playwright = browser = context = None
        failed = False
        try:
            async with asyncio.timeout(600):
                playwright, browser, context = await _open_browser()
                origin = _origin(task.environment_snapshot["base_url"])
                async def route_handler(route):
                    if _origin(route.request.url) != origin:
                        await route.abort("blockedbyclient")
                    else:
                        await route.continue_()
                await context.route("**/*", route_handler)
                await context.tracing.start(screenshots=True, snapshots=True, sources=False)
                page = await context.new_page()
                allowed_paths = [urlsplit(item["page"]["url"]).path or "/" for item in task.scenario_snapshot.get("steps", [])]
                sequence = 0
                for scenario_step in task.scenario_snapshot.get("steps", []):
                    page_info = scenario_step["page"]
                    page_url = urljoin(task.environment_snapshot["base_url"].rstrip("/") + "/", page_info["url"])
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                    _assert_allowed_url(page.url, origin, allowed_paths)
                    for detail in scenario_step["page_step"].get("details", []):
                        sequence += 1
                        await db.refresh(task)
                        if task.cancel_requested:
                            task.status = "canceled"
                            break
                        action = {"operation": detail["operation"], "locator": None, "value": (detail.get("input_value") or {}).get("value")}
                        if detail.get("element_id"):
                            element = scenario_step["elements"].get(detail["element_id"])
                            if not element:
                                raise RuntimeError("UI_ELEMENT_SNAPSHOT_INVALID")
                            action["locator"] = element["primary_locator"]
                            action["locators"] = [element["primary_locator"], *(element.get("fallback_locators") or [])]
                            action["iframe_locator"] = element.get("iframe_locator")
                        row = UiExecutionStep(project_id=task.project_id, execution_id=task.id, seq=sequence,
                                              name=detail.get("description") or detail["operation"], status="running",
                                              action_snapshot=mask_data(deepcopy(action)), started_at=datetime.now(UTC))
                        db.add(row)
                        await db.flush()
                        await _emit(db, task, "step_update", {"seq": sequence, "status": "running"})
                        try:
                            result = await _run_action(page, action, origin, allowed_paths)
                            row.status, row.result_snapshot = "passed", mask_data(result)
                        except Exception as exc:
                            code = str(exc)[:64]
                            row.status, row.error_category, row.error_message = "failed", _failure_category(code), "页面动作或断言失败"
                            failed = True
                        row.result_snapshot["dom_summary"] = mask_sensitive_text(await page.locator("body").inner_text(timeout=5000))
                        png = await _mask_screenshot(page)
                        evidence_id = await _record_evidence(db, task.project_id, "execution_step", row.id, "screenshot", png, "png", task.created_by)
                        dom_id = await _record_evidence(db, task.project_id, "execution_step", row.id, "dom_summary", row.result_snapshot["dom_summary"].encode(), "txt", task.created_by)
                        row.evidence_refs = [evidence_id, dom_id]
                        row.finished_at = datetime.now(UTC)
                        row.duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
                        task.heartbeat_at = datetime.now(UTC)
                        task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
                        await _emit(db, task, "step_update", {"seq": sequence, "status": row.status, "duration_ms": row.duration_ms})
                        if failed:
                            break
                    if failed or task.status == "canceled":
                        break
                if task.status != "canceled":
                    task.status = "failed" if failed else "completed"
                manifest_steps = list((await db.scalars(select(UiExecutionStep).where(
                    UiExecutionStep.execution_id == task.id).order_by(UiExecutionStep.seq))).all())
                manifest = mask_data({"execution_id": task.id, "scenario_revision": task.scenario_snapshot.get("revision"),
                    "steps": [{"seq": item.seq, "status": item.status, "duration_ms": item.duration_ms,
                               "error_category": item.error_category} for item in manifest_steps]})
                task.trace_manifest_ref = await _record_evidence(db, task.project_id, "execution", task.id,
                    "trace_manifest", json.dumps(manifest, ensure_ascii=False).encode(), "json", task.created_by)
                trace = get_settings().upload_root / f"tmp-ui-{task.id}.zip"
                await context.tracing.stop(path=str(trace))
                if trace.exists():
                    trace.unlink(missing_ok=True)
        except TimeoutError:
            task.status, task.error_category, task.error_message = "failed", "PAGE_LOAD_ERROR", "UI 执行总超时"
        except Exception as exc:
            task.status, task.error_category, task.error_message = "failed", _failure_category(str(exc)), "UI actuator 浏览器异常"
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()
            if playwright is not None:
                await playwright.stop()
            task.finished_at = datetime.now(UTC)
            task.lease_token = None
            task.lease_expires_at = None
            await _ensure_ui_report(db, task)
            if task.status == "failed":
                existing_repair = await db.scalar(select(UiAutomationCandidate).where(
                    UiAutomationCandidate.project_id == task.project_id, UiAutomationCandidate.execution_id == task.id,
                    UiAutomationCandidate.candidate_type == "repair"))
                if existing_repair is None:
                    repair = UiAutomationCandidate(project_id=task.project_id, execution_id=task.id,
                        candidate_type="repair", status="generating", content={"instruction": "仅根据失败证据生成局部修复候选"},
                        created_by=task.created_by)
                    db.add(repair)
                    await db.commit()
                    enqueue_ui_actuator("app.ui_worker_jobs.generate_ui_candidate_job", repair.id, 180)
            await _emit(db, task, "execution_update", {"status": task.status, "finished_at": task.finished_at.isoformat()})


def generate_ui_candidate_job(candidate_id: str) -> None:
    asyncio.run(_generate_candidate(candidate_id))


async def _generate_candidate(candidate_id: str) -> None:
    """Generate a masked, non-executable proposal. The approval API never writes assets."""
    async with worker_db_session() as db:
        row = await db.get(UiAutomationCandidate, candidate_id)
        if not row or row.status != "generating":
            return
        try:
            await generate_candidate(db, row)
        except Exception as exc:
            row.status = "failed"
            row.content = {"error_code": getattr(exc, "code", "UI_MODEL_FAILED"), "message": "候选生成失败，未写入任何资产"}
        await db.commit()
