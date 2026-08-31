from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.database import worker_db_session
from app.errors import AppError
from app.models import LocatorVerification, UiElement
from app.services.ui_verification import PlaywrightVerifier, mask_sensitive_text, safe_url


def run_verification_job(verification_id: str) -> None:
    asyncio.run(_run_verification(verification_id))


async def _run_verification(verification_id: str) -> None:
    async with worker_db_session() as db:
        row = await db.scalar(select(LocatorVerification).where(LocatorVerification.id == verification_id).with_for_update())
        if row is None or row.status not in {"pending", "running"} or row.cancel_requested:
            return
        row.status = "running"
        await db.commit()
        result = None
        error = None
        try:
            path = get_settings().upload_root / "ui-verifications" / row.project_id / f"verification-{row.id}-{time.time_ns()}.png"
            verification_task = asyncio.create_task(PlaywrightVerifier().verify(
                row.target_url, row.locator, row.iframe_locator,
                {"navigation": row.navigation_timeout_ms, "operation": row.operation_timeout_ms,
                 "total": row.total_timeout_ms}, path,
            ))
            while not verification_task.done():
                await asyncio.wait({verification_task}, timeout=0.25)
                await db.refresh(row, attribute_names=["cancel_requested"])
                if row.cancel_requested:
                    verification_task.cancel()
                    await asyncio.gather(verification_task, return_exceptions=True)
                    row.status = "canceled"
                    await db.commit()
                    return
            result = await verification_task
        except AppError as exc:
            error = exc
        except Exception as exc:
            error = AppError("UI_BROWSER_ERROR", "浏览器验证失败", 422, {"type": type(exc).__name__})

        await db.refresh(row)
        if row.cancel_requested:
            row.status = "canceled"
            await db.commit()
            return
        successful = bool(result and (row.locator is None or (
            result.match_count == 1 and result.visible and result.actionable)))
        dom_summary = mask_sensitive_text(result.dom_summary) if result and result.dom_summary is not None else None
        row.status = "passed" if successful else "failed"
        row.actual_url = safe_url(result.actual_url) if result and result.actual_url else None
        row.match_count = result.match_count if result else None
        row.visible = result.visible if result else None
        row.actionable = result.actionable if result else None
        row.dom_summary = dom_summary
        row.dom_fingerprint = hashlib.sha256((dom_summary or "").encode()).hexdigest() if dom_summary is not None else None
        row.evidence_ref = result.evidence_path.relative_to(get_settings().upload_root).as_posix() if result and result.evidence_path else None
        row.error_code = error.code if error else None
        row.error_message = mask_sensitive_text(error.message) if error else None
        if row.element_id and successful:
            element = await db.scalar(select(UiElement).where(
                UiElement.id == row.element_id, UiElement.project_id == row.project_id))
            if element and element.revision == row.element_revision and element.primary_locator == row.locator and element.iframe_locator == row.iframe_locator:
                element.verified = True
                element.verified_url = row.actual_url
                element.dom_fingerprint = row.dom_fingerprint
                element.last_verified_at = datetime.now(UTC)
        await db.commit()
