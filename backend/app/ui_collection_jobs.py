from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime

from app.database import worker_db_session
from app.models.ui_collection import (UiCollectedElement, UiCollectedPage, UiCollectionSession,
    UiCollectionSnapshot, UiLocatorCandidate)
from app.schemas.ui_collection import CollectedElementPayload
from app.services.ui_collection import locator_candidates
from app.config import get_settings
from app.errors import AppError
from app.services.ui_verification import PlaywrightVerifier, _origin, mask_sensitive_text, safe_url
from app.ui_worker_jobs import _mask_screenshot, _record_evidence

SELECTOR = "button,input,textarea,select,a,[role],[data-testid],[contenteditable=true]"
SCRIPT = """(nodes) => nodes.map((node, index) => { const style=getComputedStyle(node); const r=node.getBoundingClientRect(); const label=node.getAttribute('aria-label')||''; const text=(node.innerText||'').trim().slice(0,512); return {element_key:'e_'+index,tag:node.tagName.toLowerCase(),role:node.getAttribute('role')||null,accessible_name:(label||text||node.getAttribute('placeholder')||'').slice(0,512),attributes:{test_id:node.getAttribute('data-testid')||node.getAttribute('data-test-id'),id:node.id||null,name:node.getAttribute('name'),label:label||null,placeholder:node.getAttribute('placeholder'),text:text},visible:style.visibility!=='hidden'&&style.display!=='none'&&r.width>0&&r.height>0,enabled:!node.disabled,actionable:!node.disabled&&style.pointerEvents!=='none',checked:typeof node.checked==='boolean'?node.checked:null}; })"""


def run_collection_job(session_id: str) -> None:
    asyncio.run(_run(session_id))


def verify_collection_candidate_job(candidate_id: str) -> None:
    asyncio.run(_verify_candidate(candidate_id))


async def _verify_candidate(candidate_id: str) -> None:
    async with worker_db_session() as db:
        candidate = await db.get(UiLocatorCandidate, candidate_id)
        if not candidate or candidate.status != "verifying": return
        snapshot = await db.get(UiCollectionSnapshot, candidate.snapshot_id)
        if snapshot is None:
            candidate.status, candidate.validation_result = "failed", {"error_code": "UI_SNAPSHOT_NOT_FOUND"}; await db.commit(); return
        path = get_settings().upload_root / "ui-verifications" / candidate.project_id / f"candidate-{candidate.id}.png"
        try:
            result = await PlaywrightVerifier().verify(snapshot.actual_url, candidate.locator, candidate.frame_path,
                {"navigation": 30000, "operation": 5000, "total": 60000}, path)
            passed = result.match_count == 1 and result.visible is True and result.actionable is True
            candidate.status = "passed" if passed else "failed"
            candidate.validation_result = {"match_count": result.match_count, "visible": result.visible,
                "actionable": result.actionable, "actual_url": safe_url(result.actual_url or snapshot.actual_url),
                "dom_fingerprint": hashlib.sha256((result.dom_summary or "").encode()).hexdigest(),
                "evidence_ref": path.relative_to(get_settings().upload_root).as_posix() if path.exists() else None}
        except AppError as exc:
            candidate.status, candidate.validation_result = "failed", {"error_code": exc.code, "error_message": mask_sensitive_text(exc.message)}
        await db.commit()


async def _run(session_id: str) -> None:
    async with worker_db_session() as db:
        session = await db.get(UiCollectionSession, session_id)
        if not session or session.status != "pending": return
        session.status = "running"; await db.commit()
        playwright = browser = context = None
        try:
            from playwright.async_api import async_playwright
            async with asyncio.timeout(session.total_timeout_ms / 1000):
                playwright = await async_playwright().start(); browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(ignore_https_errors=False); origin = _origin(session.start_url)
                async def route_handler(route):
                    await (route.continue_() if _origin(route.request.url) == origin else route.abort("blockedbyclient"))
                await context.route("**/*", route_handler)
                page = await context.new_page(); await page.goto(session.start_url, wait_until="domcontentloaded", timeout=min(30000, session.total_timeout_ms))
                if _origin(page.url) != origin: raise RuntimeError("UI_REDIRECT_FORBIDDEN")
                cdp = await context.new_cdp_session(page)
                ax = await cdp.send("Accessibility.getFullAXTree")
                ax = json.loads(mask_sensitive_text(json.dumps(ax, ensure_ascii=False)))
                snapshot = UiCollectionSnapshot(project_id=session.project_id, session_id=session.id, revision=1,
                    actual_url=safe_url(page.url), title=mask_sensitive_text(await page.title()), accessibility_tree=ax,
                    dom_inventory=[], evidence_refs=[], created_by=session.created_by)
                db.add(snapshot); await db.flush()
                all_inventory = []
                frames = page.frames[:session.max_iframes + 1]
                for frame_index, frame in enumerate(frames):
                    frame_path = []
                    if frame != page.main_frame:
                        frame_el = await frame.frame_element()
                        test_id = await frame_el.get_attribute("data-testid")
                        element_id = await frame_el.get_attribute("id")
                        frame_path = [{"type": "test_id", "value": test_id}] if test_id else ([{"type": "id", "value": element_id}] if element_id else [])
                        if not frame_path: continue
                    raw = await frame.locator(SELECTOR).evaluate_all(SCRIPT)
                    page_row = UiCollectedPage(project_id=session.project_id, snapshot_id=snapshot.id,
                        page_key=f"frame-{frame_index}", url=safe_url(frame.url), title=snapshot.title if frame_index == 0 else "iframe",
                        frame_path=frame_path, created_by=session.created_by)
                    db.add(page_row); await db.flush()
                    for index, value in enumerate(raw[:session.max_elements_per_page]):
                        value["element_key"] = f"f{frame_index}_{index}"; value["frame_path"] = frame_path
                        payload = CollectedElementPayload.model_validate(value)
                        attrs = json.loads(mask_sensitive_text(json.dumps(payload.attributes.model_dump(), ensure_ascii=False)))
                        fingerprint = hashlib.sha256(json.dumps({"tag": payload.tag, "role": payload.role, "attrs": attrs}, sort_keys=True).encode()).hexdigest()
                        element = UiCollectedElement(project_id=session.project_id, snapshot_id=snapshot.id,
                            collected_page_id=page_row.id, element_key=payload.element_key, tag=payload.tag, role=payload.role,
                            accessible_name=mask_sensitive_text(payload.accessible_name), attributes=attrs, visible=payload.visible,
                            enabled=payload.enabled, actionable=payload.actionable, checked=payload.checked,
                            frame_path=frame_path, dom_fingerprint=fingerprint, created_by=session.created_by)
                        db.add(element); await db.flush()
                        candidate_input = {**payload.model_dump(), "attributes": attrs}
                        specs = locator_candidates(candidate_input)
                        for priority, spec in enumerate(specs, start=1):
                            db.add(UiLocatorCandidate(project_id=session.project_id, snapshot_id=snapshot.id,
                                collected_element_id=element.id, priority=priority, locator=spec, frame_path=frame_path,
                                created_by=session.created_by))
                        all_inventory.append({"element_key": payload.element_key, "tag": payload.tag, "role": payload.role,
                            "accessible_name": element.accessible_name, "attributes": attrs, "visible": payload.visible,
                            "enabled": payload.enabled, "actionable": payload.actionable, "frame_path": frame_path,
                            "locator_candidates": specs})
                snapshot.dom_inventory = all_inventory
                screenshot_id = await _record_evidence(db, session.project_id, "collection_snapshot", snapshot.id,
                    "screenshot", await _mask_screenshot(page), "png", session.created_by)
                dom_id = await _record_evidence(db, session.project_id, "collection_snapshot", snapshot.id,
                    "dom_inventory", json.dumps(all_inventory, ensure_ascii=False).encode(), "json", session.created_by)
                snapshot.evidence_refs = [screenshot_id, dom_id]
                session.status = "completed"
        except TimeoutError:
            session.status, session.error_code, session.error_message = "timeout", "UI_COLLECTION_TIMEOUT", "UI 页面采集超时"
        except Exception as exc:
            session.status, session.error_code, session.error_message = "failed", str(exc)[:64], "UI 页面采集失败"
        finally:
            if context: await context.close()
            if browser: await browser.close()
            if playwright: await playwright.stop()
            session.finished_at = datetime.now(UTC); await db.commit()
