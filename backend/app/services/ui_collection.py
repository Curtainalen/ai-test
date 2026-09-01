from __future__ import annotations

import re
from sqlalchemy import func, select

from app.errors import AppError
from app.models import TestEnvironment, UiElement
from app.models.ui_collection import (UiCollectedElement, UiCollectedPage, UiCollectionSession,
    UiCollectionSnapshot, UiLocatorCandidate, UiLocatorRevision)
from app.services.identity import require_membership
from app.services.queue import enqueue_ui_actuator
from app.services.ui_verification import resolve_target_url, safe_url


def locator_candidates(element: dict) -> list[dict]:
    attrs, tag = element.get("attributes", {}), element.get("tag", "*")
    result: list[dict] = []
    def add(spec):
        if spec and spec not in result:
            result.append(spec)
    if attrs.get("test_id"): add({"type": "test_id", "value": attrs["test_id"]})
    stable_id = attrs.get("id")
    if stable_id and len(stable_id) <= 128 and not re.search(r"[a-f0-9]{16,}|\d{8,}", stable_id, re.I):
        add({"type": "id", "value": stable_id})
    if element.get("role") and element.get("accessible_name"):
        add({"type": "role", "value": element["role"], "name": element["accessible_name"], "exact": True})
    if attrs.get("label"): add({"type": "label", "value": attrs["label"], "exact": True})
    if attrs.get("placeholder"): add({"type": "placeholder", "value": attrs["placeholder"], "exact": True})
    if attrs.get("name"): add({"type": "name", "value": attrs["name"]})
    if attrs.get("name"): add({"type": "css", "value": f'{tag}[name="{_css(attrs["name"])}"]'})
    if stable_id: add({"type": "xpath", "value": f'//*[@id="{stable_id.replace(chr(34), "")}"]'})
    return result


def _css(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\A ")


def session_view(row):
    return {"id": row.id, "project_id": row.project_id, "environment_id": row.environment_id,
            "start_url": row.start_url, "allowed_paths": row.allowed_paths, "status": row.status,
            "revision": row.revision, "error_code": row.error_code, "error_message": row.error_message,
            "created_by": row.created_by, "created_at": row.created_at.isoformat() if row.created_at else None}


async def create(db, project_id, user, data):
    await require_membership(db, project_id, user)
    environment = await db.scalar(select(TestEnvironment).where(TestEnvironment.id == data.environment_id,
        TestEnvironment.project_id == project_id, TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    target = await resolve_target_url(environment, "/", data.start_url)
    row = UiCollectionSession(project_id=project_id, environment_id=environment.id, start_url=safe_url(target),
        allowed_paths=data.allowed_paths, max_pages=data.max_pages, max_elements_per_page=data.max_elements_per_page,
        max_iframes=data.max_iframes, total_timeout_ms=data.total_timeout_ms, created_by=user.id)
    db.add(row); await db.commit()
    enqueue_ui_actuator("app.ui_collection_jobs.run_collection_job", row.id, data.total_timeout_ms // 1000 + 30)
    return session_view(row)


async def detail(db, project_id, user, session_id):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(UiCollectionSession).where(UiCollectionSession.id == session_id,
                                                             UiCollectionSession.project_id == project_id))
    if row is None: raise AppError("RESOURCE_NOT_FOUND", "UI 采集会话不存在", 404)
    snapshots = list((await db.scalars(select(UiCollectionSnapshot).where(UiCollectionSnapshot.session_id == row.id,
        UiCollectionSnapshot.project_id == project_id).order_by(UiCollectionSnapshot.revision))).all())
    data = session_view(row); data["snapshots"] = []
    for snapshot in snapshots:
        elements = list((await db.scalars(select(UiCollectedElement).where(UiCollectedElement.snapshot_id == snapshot.id,
            UiCollectedElement.project_id == project_id).order_by(UiCollectedElement.element_key))).all())
        element_ids = [item.id for item in elements]
        candidates = list((await db.scalars(select(UiLocatorCandidate).where(UiLocatorCandidate.collected_element_id.in_(element_ids),
            UiLocatorCandidate.project_id == project_id).order_by(UiLocatorCandidate.collected_element_id, UiLocatorCandidate.priority))).all()) if element_ids else []
        by_element = {}
        for item in candidates: by_element.setdefault(item.collected_element_id, []).append({"id": item.id, "priority": item.priority, "locator": item.locator, "status": item.status})
        data["snapshots"].append({"id": snapshot.id, "revision": snapshot.revision, "actual_url": snapshot.actual_url,
            "title": snapshot.title, "accessibility_tree": snapshot.accessibility_tree, "dom_inventory": snapshot.dom_inventory,
            "elements": [{"id": item.id, "element_key": item.element_key, "tag": item.tag, "role": item.role,
                "accessible_name": item.accessible_name, "attributes": item.attributes, "visible": item.visible,
                "enabled": item.enabled, "actionable": item.actionable, "frame_path": item.frame_path,
                "locator_candidates": by_element.get(item.id, [])} for item in elements]})
    return data


async def request_candidate_verification(db, project_id, user, candidate_id):
    await require_membership(db, project_id, user)
    row = await db.scalar(select(UiLocatorCandidate).where(UiLocatorCandidate.id == candidate_id,
                                                            UiLocatorCandidate.project_id == project_id))
    if row is None: raise AppError("RESOURCE_NOT_FOUND", "Locator 候选不存在", 404)
    if row.status not in {"draft", "failed"}: raise AppError("UI_LOCATOR_CANDIDATE_NOT_VERIFIABLE", "Locator 候选当前不能验证", 409)
    row.status = "verifying"; row.validation_result = {}; await db.commit()
    enqueue_ui_actuator("app.ui_collection_jobs.verify_collection_candidate_job", row.id, 90)
    return {"id": row.id, "status": row.status}


async def propose_revision(db, project_id, user, candidate_id, element_id):
    await require_membership(db, project_id, user)
    candidate = await db.scalar(select(UiLocatorCandidate).where(UiLocatorCandidate.id == candidate_id,
                                                                  UiLocatorCandidate.project_id == project_id))
    element = await db.scalar(select(UiElement).where(UiElement.id == element_id, UiElement.project_id == project_id))
    if candidate is None or element is None: raise AppError("RESOURCE_NOT_FOUND", "Locator 候选或正式元素不存在", 404)
    if candidate.status != "passed": raise AppError("UI_LOCATOR_CANDIDATE_NOT_PASSED", "只有验证通过的候选可创建 revision", 409)
    revision = int(await db.scalar(select(func.max(UiLocatorRevision.revision)).where(
        UiLocatorRevision.project_id == project_id, UiLocatorRevision.ui_element_id == element.id)) or 0) + 1
    row = UiLocatorRevision(project_id=project_id, ui_element_id=element.id, source_candidate_id=candidate.id,
        revision=revision, primary_locator=candidate.locator, fallback_locators=[], created_by=user.id)
    db.add(row); await db.commit()
    return {"id": row.id, "revision": row.revision, "status": row.status, "primary_locator": row.primary_locator}


async def decide_revision(db, project_id, user, revision_id, decision):
    from datetime import UTC, datetime
    await require_membership(db, project_id, user)
    row = await db.scalar(select(UiLocatorRevision).where(UiLocatorRevision.id == revision_id,
                                                           UiLocatorRevision.project_id == project_id))
    if row is None: raise AppError("RESOURCE_NOT_FOUND", "Locator revision 不存在", 404)
    if row.status != "pending_review": raise AppError("UI_LOCATOR_REVISION_NOT_REVIEWABLE", "Locator revision 不处于待审核状态", 409)
    row.status, row.reviewed_by, row.reviewed_at = decision, user.id, datetime.now(UTC)
    if decision == "approved":
        element = await db.scalar(select(UiElement).where(UiElement.id == row.ui_element_id, UiElement.project_id == project_id))
        if element is None: raise AppError("RESOURCE_NOT_FOUND", "正式元素不存在", 404)
        element.primary_locator, element.fallback_locators = row.primary_locator, row.fallback_locators
        element.verified, element.revision = True, element.revision + 1
    await db.commit()
    return {"id": row.id, "status": row.status, "revision": row.revision}
