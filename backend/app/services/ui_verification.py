from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import AppError
from app.models import LocatorVerification, TestEnvironment, UiElement, UiPage, User
from app.services.identity import require_membership
from app.services.masking import MASK, mask_url
from app.services.queue import enqueue_ui_actuator
from app.services.remote_openapi import _is_forbidden_address, resolve_host_addresses
from app.services.ui_assets import _one, verification_view

_project_limits: dict[str, asyncio.Semaphore] = {}
_limit_guard = asyncio.Lock()


@dataclass
class BrowserVerificationResult:
    actual_url: str | None = None
    match_count: int | None = None
    visible: bool | None = None
    actionable: bool | None = None
    dom_summary: str | None = None
    evidence_path: Path | None = None


def safe_url(value: str) -> str:
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError:
        return "invalid-url"
    host = (parts.hostname or "").lower()
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", mask_url(value).split("?", 1)[1] if "?" in mask_url(value) else "", ""))


def mask_sensitive_text(value: str) -> str:
    value = re.sub(r'(?i)("?(?:password|passwd|pwd|token|authorization|cookie|secret|api[_-]?key)"?\s*[:=]\s*["\']?)([^\s,;"\']+)', rf"\1{MASK}", value)
    value = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', MASK, value)
    value = re.sub(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)', MASK, value)
    return value[:10000]


def _origin(value: str) -> tuple[str, str, int]:
    parts = urlsplit(value)
    return parts.scheme.lower(), (parts.hostname or "").lower().rstrip("."), parts.port or (443 if parts.scheme.lower() == "https" else 80)


async def resolve_target_url(environment: TestEnvironment, page_url: str, override: str | None) -> str:
    raw = (override or page_url).strip()
    base = environment.base_url.rstrip("/") + "/"
    candidate = urljoin(base, raw)
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise AppError("UI_TARGET_URL_FORBIDDEN", "页面 URL 必须是无凭据的 HTTP/HTTPS 地址", 422)
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise AppError("UI_TARGET_URL_FORBIDDEN", "页面 URL 端口无效", 422) from exc
    if _origin(candidate) != _origin(environment.base_url):
        raise AppError("UI_TARGET_URL_FORBIDDEN", "页面 URL 必须属于所选环境的目标域名", 403)
    addresses = await resolve_host_addresses(parts.hostname, port)
    if not addresses or any(_is_forbidden_address(address) for address in addresses):
        raise AppError("UI_TARGET_URL_FORBIDDEN", "页面 URL 解析到内网、回环或保留地址", 403)
    return candidate


async def _project_semaphore(project_id: str) -> asyncio.Semaphore:
    settings = get_settings()
    async with _limit_guard:
        return _project_limits.setdefault(project_id, asyncio.Semaphore(settings.ui_verification_project_concurrency))


def _locator(root, spec: dict):
    kind, value = spec["type"], spec["value"]
    exact = bool(spec.get("exact"))
    if kind in {"test_id", "data_testid"}:
        return root.get_by_test_id(value)
    if kind == "id":
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\A ")
        return root.locator(f'[id="{escaped}"]')
    if kind == "role":
        return root.get_by_role(value, name=spec.get("name"), exact=exact)
    if kind == "label":
        return root.get_by_label(value, exact=exact)
    if kind == "placeholder":
        return root.get_by_placeholder(value, exact=exact)
    if kind == "name":
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\A ")
        return root.locator(f'[name="{escaped}"]')
    if kind == "css":
        return root.locator(value)
    return root.locator(f"xpath={value}")


async def _frame_root(page, spec: dict | None):
    if not spec:
        return page
    root = page
    for frame_spec in spec if isinstance(spec, list) else [spec]:
        frame_element = _locator(root, frame_spec)
        if await frame_element.count() != 1:
            raise AppError("UI_IFRAME_NOT_UNIQUE", "iframe 定位器必须唯一匹配一个 iframe", 422)
        content_frame = getattr(frame_element, "content_frame", None)
        if content_frame is None:
            raise AppError("UI_IFRAME_UNAVAILABLE", "iframe 不可访问", 422)
        root = content_frame() if callable(content_frame) else content_frame
        if inspect.isawaitable(root): root = await root
        if root is None: raise AppError("UI_IFRAME_UNAVAILABLE", "iframe 内容尚不可访问", 422)
    return root


class PlaywrightVerifier:
    """Loads Playwright only in the verification path so API-only deployments stay usable."""

    async def verify(self, target_url: str, locator: dict | None, iframe_locator: dict | None, timeouts: dict, evidence_path: Path) -> BrowserVerificationResult:
        try:
            from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, async_playwright
        except ImportError as exc:
            raise AppError("UI_PLAYWRIGHT_UNAVAILABLE", "当前运行环境未安装 Python Playwright", 503) from exc

        result = BrowserVerificationResult()
        browser = context = page = None
        try:
            async with asyncio.timeout(timeouts["total"] / 1000):
                async with async_playwright() as playwright:
                    browser = await playwright.chromium.launch(headless=True)
                    context = await browser.new_context(ignore_https_errors=False)
                    allowed_origin = _origin(target_url)

                    async def restrict_network(route):
                        request_parts = urlsplit(route.request.url)
                        if _origin(route.request.url) != allowed_origin:
                            await route.abort("blockedbyclient")
                        elif request_parts.username or request_parts.password:
                            await route.abort("blockedbyclient")
                        else:
                            await route.continue_()

                    await context.route("**/*", restrict_network)
                    page = await context.new_page()
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=timeouts["navigation"])
                    result.actual_url = page.url
                    if _origin(result.actual_url) != allowed_origin:
                        raise AppError("UI_REDIRECT_FORBIDDEN", "页面重定向到了未授权域名", 403)
                    body_text = await page.locator("body").inner_text(timeout=timeouts["operation"])
                    result.dom_summary = mask_sensitive_text(body_text)
                    if locator:
                        root = await _frame_root(page, iframe_locator)
                        target = _locator(root, locator)
                        result.match_count = await target.count()
                        if result.match_count == 1:
                            result.visible = await target.is_visible()
                            result.actionable = bool(result.visible and await target.is_enabled())
                    evidence_path.parent.mkdir(parents=True, exist_ok=True)
                    # This fixed redaction leaves layout evidence while suppressing
                    # page text and media; no user-supplied script is executed.
                    await page.add_style_tag(content="* { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; } img, video, canvas { filter: blur(32px) !important; } input, textarea { caret-color: transparent !important; }")
                    await page.locator('input[type="password"], input[autocomplete="current-password"], input[autocomplete="new-password"]').evaluate_all("nodes => nodes.forEach(node => { node.value = ''; node.style.webkitTextSecurity = 'disc'; })")
                    await page.screenshot(path=str(evidence_path), full_page=False, timeout=timeouts["operation"])
                    result.evidence_path = evidence_path
        except AppError:
            raise
        except (PlaywrightTimeoutError, TimeoutError) as exc:
            raise AppError("UI_VERIFICATION_TIMEOUT", "页面或定位器验证超时", 504) from exc
        except PlaywrightError as exc:
            raise AppError("UI_BROWSER_ERROR", "浏览器验证失败", 422, {"type": type(exc).__name__}) from exc
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()
        return result


async def _persist(db: AsyncSession, project_id: str, user: User, page: UiPage, element: UiElement | None, locator: dict | None, iframe_locator: dict | None, target_url: str, result: BrowserVerificationResult | None, error: AppError | None) -> dict:
    successful = bool(result and (locator is None or (result.match_count == 1 and result.visible and result.actionable)))
    # Persisted evidence is masked again so alternate verifier implementations
    # cannot accidentally bypass the browser adapter's redaction.
    dom_summary = mask_sensitive_text(result.dom_summary) if result and result.dom_summary is not None else None
    fingerprint = hashlib.sha256((dom_summary or "").encode()).hexdigest() if dom_summary is not None else None
    evidence_ref = None
    if result and result.evidence_path:
        evidence_ref = result.evidence_path.relative_to(get_settings().upload_root).as_posix()
    row = LocatorVerification(
        project_id=project_id,
        page_id=page.id,
        element_id=element.id if element else None,
        element_revision=element.revision if element else None,
        locator=locator,
        iframe_locator=iframe_locator,
        target_url=safe_url(target_url),
        actual_url=safe_url(result.actual_url) if result and result.actual_url else None,
        status="passed" if successful else "failed",
        match_count=result.match_count if result else None,
        visible=result.visible if result else None,
        actionable=result.actionable if result else None,
        dom_fingerprint=fingerprint,
        dom_summary=dom_summary,
        evidence_ref=evidence_ref,
        error_code=error.code if error else None,
        error_message=mask_sensitive_text(error.message) if error else None,
        created_by=user.id,
    )
    db.add(row)
    if element and successful and locator == element.primary_locator and iframe_locator == element.iframe_locator:
        element.verified = True
        element.verified_url = row.actual_url
        element.dom_fingerprint = fingerprint
        element.last_verified_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return verification_view(row)


async def _request_verification(db: AsyncSession, project_id: str, user: User, page: UiPage,
                                environment: TestEnvironment, data, locator: dict | None,
                                iframe_locator: dict | None, element: UiElement | None = None) -> dict:
    resolved = await resolve_target_url(environment, page.url, data.target_url)
    row = LocatorVerification(
        project_id=project_id, environment_id=environment.id, page_id=page.id,
        element_id=element.id if element else None,
        element_revision=element.revision if element else None,
        locator=locator, iframe_locator=iframe_locator, target_url=safe_url(resolved), status="pending",
        navigation_timeout_ms=data.navigation_timeout_ms, operation_timeout_ms=data.operation_timeout_ms,
        total_timeout_ms=data.total_timeout_ms, cancel_requested=False, created_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    try:
        enqueue_ui_actuator("app.ui_verification_jobs.run_verification_job", row.id,
                            max(30, data.total_timeout_ms // 1000 + 30))
    except AppError as exc:
        row.status, row.error_code, row.error_message = "failed", exc.code, exc.message
        await db.commit()
        raise
    return verification_view(row)


async def request_page_verification(db: AsyncSession, project_id: str, user: User, page_id: str, data) -> dict:
    await require_membership(db, project_id, user)
    page = await _one(db, UiPage, project_id, page_id, "UI 页面")
    environment = await db.scalar(select(TestEnvironment).where(
        TestEnvironment.id == data.environment_id, TestEnvironment.project_id == project_id,
        TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    return await _request_verification(db, project_id, user, page, environment, data, None, None)


async def request_locator_verification(db: AsyncSession, project_id: str, user: User, page_id: str, data) -> dict:
    await require_membership(db, project_id, user)
    page = await _one(db, UiPage, project_id, page_id, "UI 页面")
    environment = await db.scalar(select(TestEnvironment).where(
        TestEnvironment.id == data.environment_id, TestEnvironment.project_id == project_id,
        TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    return await _request_verification(db, project_id, user, page, environment, data, data.locator.model_dump(),
                                       data.iframe_locator.model_dump() if data.iframe_locator else None)


async def request_element_verification(db: AsyncSession, project_id: str, user: User, element_id: str, data) -> dict:
    await require_membership(db, project_id, user)
    element = await _one(db, UiElement, project_id, element_id, "UI 元素")
    page = await _one(db, UiPage, project_id, element.page_id, "UI 页面")
    environment = await db.scalar(select(TestEnvironment).where(
        TestEnvironment.id == data.environment_id, TestEnvironment.project_id == project_id,
        TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    return await _request_verification(db, project_id, user, page, environment, data, element.primary_locator,
                                       element.iframe_locator, element)


async def cancel_verification(db: AsyncSession, project_id: str, user: User, verification_id: str) -> dict:
    await require_membership(db, project_id, user)
    row = await db.scalar(select(LocatorVerification).where(
        LocatorVerification.id == verification_id, LocatorVerification.project_id == project_id))
    if row is None:
        raise AppError("RESOURCE_NOT_FOUND", "验证记录不存在", 404)
    if row.status not in {"pending", "running"}:
        raise AppError("UI_VERIFICATION_NOT_CANCELABLE", "验证任务已进入终态", 409)
    row.cancel_requested = True
    if row.status == "pending":
        row.status = "canceled"
    await db.commit()
    return verification_view(row)


async def verify_page(db: AsyncSession, project_id: str, user: User, page_id: str, data, verifier: PlaywrightVerifier | None = None) -> dict:
    await require_membership(db, project_id, user)
    page = await _one(db, UiPage, project_id, page_id, "UI 页面")
    environment = await db.scalar(select(TestEnvironment).where(TestEnvironment.id == data.environment_id, TestEnvironment.project_id == project_id, TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    target_url = data.target_url or page.url
    result = None
    error = None
    try:
        resolved = await resolve_target_url(environment, page.url, data.target_url)
        path = get_settings().upload_root / "ui-verifications" / project_id / f"page-{page.id}-{time.time_ns()}.png"
        async with await _project_semaphore(project_id):
            result = await (verifier or PlaywrightVerifier()).verify(resolved, None, None, {"navigation": data.navigation_timeout_ms, "operation": data.operation_timeout_ms, "total": data.total_timeout_ms}, path)
        target_url = resolved
    except AppError as exc:
        error = exc
    return await _persist(db, project_id, user, page, None, None, None, target_url, result, error)


async def verify_locator(db: AsyncSession, project_id: str, user: User, page_id: str, data, verifier: PlaywrightVerifier | None = None) -> dict:
    await require_membership(db, project_id, user)
    page = await _one(db, UiPage, project_id, page_id, "UI 页面")
    environment = await db.scalar(select(TestEnvironment).where(TestEnvironment.id == data.environment_id, TestEnvironment.project_id == project_id, TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    target_url, result, error = data.target_url or page.url, None, None
    locator = data.locator.model_dump()
    iframe_locator = data.iframe_locator.model_dump() if data.iframe_locator else None
    try:
        resolved = await resolve_target_url(environment, page.url, data.target_url)
        path = get_settings().upload_root / "ui-verifications" / project_id / f"locator-{page.id}-{time.time_ns()}.png"
        async with await _project_semaphore(project_id):
            result = await (verifier or PlaywrightVerifier()).verify(resolved, locator, iframe_locator, {"navigation": data.navigation_timeout_ms, "operation": data.operation_timeout_ms, "total": data.total_timeout_ms}, path)
        target_url = resolved
    except AppError as exc:
        error = exc
    return await _persist(db, project_id, user, page, None, locator, iframe_locator, target_url, result, error)


async def verify_element(db: AsyncSession, project_id: str, user: User, element_id: str, data, verifier: PlaywrightVerifier | None = None) -> dict:
    await require_membership(db, project_id, user)
    element = await _one(db, UiElement, project_id, element_id, "UI 元素")
    page = await _one(db, UiPage, project_id, element.page_id, "UI 页面")
    environment = await db.scalar(select(TestEnvironment).where(TestEnvironment.id == data.environment_id, TestEnvironment.project_id == project_id, TestEnvironment.is_enabled.is_(True)))
    if environment is None:
        raise AppError("UI_ENVIRONMENT_INVALID", "环境不存在、未启用或不属于当前项目", 422)
    target_url, result, error = data.target_url or page.url, None, None
    try:
        resolved = await resolve_target_url(environment, page.url, data.target_url)
        path = get_settings().upload_root / "ui-verifications" / project_id / f"element-{element.id}-{time.time_ns()}.png"
        async with await _project_semaphore(project_id):
            result = await (verifier or PlaywrightVerifier()).verify(resolved, element.primary_locator, element.iframe_locator, {"navigation": data.navigation_timeout_ms, "operation": data.operation_timeout_ms, "total": data.total_timeout_ms}, path)
        target_url = resolved
    except AppError as exc:
        error = exc
    return await _persist(db, project_id, user, page, element, element.primary_locator, element.iframe_locator, target_url, result, error)
