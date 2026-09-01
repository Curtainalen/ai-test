import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.models import TestEnvironment as EnvironmentModel, UiElement, UiPage
from app.schemas.ui import LocatorSpec, UiAutomationBundle, UiElementCreate, UiPageLocatorVerifyRequest
from app.services import ui_verification
from app.services.ui_collection import locator_candidates
from app.services.ui_verification import BrowserVerificationResult, mask_sensitive_text, safe_url
from app.ui_worker_jobs import _failure_category, _persisted_execution_action


class FakeDb:
    def __init__(self, environment):
        self.environment = environment
        self.added = []

    async def scalar(self, _statement):
        return self.environment

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        pass

    async def refresh(self, _row):
        pass


class FakeVerifier:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def verify(self, target_url, locator, iframe_locator, timeouts, evidence_path):
        self.calls.append((target_url, locator, iframe_locator, timeouts, evidence_path))
        return self.result


def test_locator_schema_and_sensitive_step_value_are_constrained():
    element = UiElementCreate(page_id="page", name="login", primary_locator={"type": "role", "value": "button", "name": "登录"})
    assert element.primary_locator.type == "role"
    with pytest.raises(ValueError):
        LocatorSpec(type="css", value="\n")
    request = UiPageLocatorVerifyRequest(environment_id="env", locator={"type": "test_id", "value": "submit"}, iframe_locator={"type": "css", "value": "iframe#main"})
    assert request.iframe_locator and request.iframe_locator.value == "iframe#main"


def test_persisted_execution_action_uses_reviewed_locator_assets_and_normalizes_assertions():
    element = {
        "primary_locator": {"type": "test_id", "value": "login-submit"},
        "fallback_locators": [{"type": "role", "value": "button", "name": "登录"}],
        "iframe_locator": [{"type": "css", "value": "iframe#shell"}],
    }
    action = _persisted_execution_action(
        {"operation": "visible", "input_value": {"value": "ignored"}}, element)
    assert action["operation"] == "assert_visible"
    assert action["locators"] == [element["primary_locator"], *element["fallback_locators"]]
    assert action["iframe_locator"] == element["iframe_locator"]
    assert action["timeout_ms"] == 8000

    assert _persisted_execution_action({"operation": "text", "input_value": {"value": "欢迎"}})["operation"] == "assert_text"
    assert _persisted_execution_action({"operation": "url", "input_value": {"value": "/dashboard"}})["operation"] == "assert_url"


def test_automation_bundle_requires_a_closed_project_scoped_asset_graph():
    bundle = UiAutomationBundle.model_validate({
        "module_name": "登录", "pages": [{"key": "login", "name": "登录页", "url": "/login"}],
        "elements": [{"key": "submit", "page_key": "login", "name": "登录按钮", "primary_locator": {"type": "test_id", "value": "login-submit"}}],
        "page_steps": [{"key": "submit_login", "page_key": "login", "name": "提交登录", "details": [{"step_sort": 1, "step_type": "action", "operation": "click", "element_key": "submit"}]}],
        "scenario_name": "用户登录", "scenario_step_keys": ["submit_login"],
    })
    assert bundle.scenario_step_keys == ["submit_login"]
    with pytest.raises(ValueError):
        UiAutomationBundle.model_validate({
            "module_name": "登录", "pages": [{"key": "login", "name": "登录页", "url": "/login"}],
            "elements": [], "page_steps": [{"key": "bad", "page_key": "login", "name": "坏步骤", "details": [{"step_sort": 1, "step_type": "action", "operation": "click", "element_key": "missing"}]}],
            "scenario_name": "用户登录", "scenario_step_keys": ["bad"],
        })


def test_sensitive_text_and_url_are_masked():
    assert "abc123" not in mask_sensitive_text('token=abc123 password: secret')
    value = safe_url("https://user:password@example.test/a?access_token=abc")
    assert "password" not in value and "abc" not in value


def test_locator_candidates_follow_stable_priority_and_drop_dynamic_id():
    candidates = locator_candidates({
        "tag": "input", "role": "textbox", "accessible_name": "用户名",
        "attributes": {"test_id": "login-user", "id": "field-0123456789abcdef", "label": "用户名",
                       "name": "username", "placeholder": "请输入用户名"},
    })
    assert [item["type"] for item in candidates] == ["test_id", "role", "label", "placeholder", "name", "css", "xpath"]
    assert all(item.get("value") != "field-0123456789abcdef" for item in candidates if item["type"] == "id")


def test_nested_iframe_path_is_resolved_in_order():
    class FrameElement:
        def __init__(self, child): self.content_frame = child
        async def count(self): return 1
    class Root:
        def __init__(self, name): self.name, self.calls = name, []
        def locator(self, value):
            self.calls.append(value)
            return FrameElement(inner if self is page else leaf)
    page, inner, leaf = Root("page"), Root("inner"), Root("leaf")
    result = asyncio.run(ui_verification._frame_root(page, [{"type": "css", "value": "iframe.outer"}, {"type": "css", "value": "iframe.inner"}]))
    assert result is leaf
    assert page.calls == ["iframe.outer"] and inner.calls == ["iframe.inner"]


def test_ui_failure_categories_are_stable():
    assert _failure_category("UI_LOCATOR_NOT_FOUND") == "LOCATOR_BROKEN"
    assert _failure_category("UI_SECRET_UNRESOLVED") == "AUTH_FAILED"
    assert _failure_category("UI_ASSERTION_FAILED") == "EXPECTATION_MISMATCH"
    assert _failure_category("UI_BROWSER_CRASH") == "ACTUATOR_ERROR"


def test_verify_element_marks_only_unique_visible_actionable_locator(monkeypatch):
    element = UiElement(id="element", project_id="project", page_id="page", name="login", primary_locator={"type": "test_id", "value": "login"}, fallback_locators=[], iframe_locator={"type": "css", "value": "iframe"}, revision=3, verified=False, created_by="user")
    page = UiPage(id="page", project_id="project", module_id="module", name="login", url="/login", created_by="user")
    environment = EnvironmentModel(id="env", project_id="project", name="test", base_url="https://example.test", created_by="user")
    verifier = FakeVerifier(BrowserVerificationResult(actual_url="https://example.test/login", match_count=1, visible=True, actionable=True, dom_summary="hello"))
    db = FakeDb(environment)

    async def one(_db, _model, _project_id, row_id, _label):
        return element if row_id == "element" else page

    async def target(_environment, _page_url, _override):
        return "https://example.test/login"

    monkeypatch.setattr(ui_verification, "_one", one)
    monkeypatch.setattr(ui_verification, "require_membership", lambda *_: asyncio.sleep(0))
    monkeypatch.setattr(ui_verification, "resolve_target_url", target)
    data = SimpleNamespace(environment_id="env", target_url=None, navigation_timeout_ms=1000, operation_timeout_ms=1000, total_timeout_ms=1000)
    result = asyncio.run(ui_verification.verify_element(db, "project", SimpleNamespace(id="user"), "element", data, verifier))

    assert result["status"] == "passed"
    assert element.verified is True
    assert db.added[0].element_revision == 3
    assert verifier.calls[0][2] == {"type": "css", "value": "iframe"}


def test_element_verification_request_is_queued_without_starting_browser(monkeypatch):
    element = UiElement(id="element", project_id="project", page_id="page", name="login",
                        primary_locator={"type": "test_id", "value": "login"}, fallback_locators=[],
                        iframe_locator=None, revision=3, verified=False, created_by="user")
    page = UiPage(id="page", project_id="project", module_id="module", name="login", url="/login", created_by="user")
    environment = EnvironmentModel(id="env", project_id="project", name="test", base_url="https://example.test", created_by="user")
    db = FakeDb(environment)
    queued = []

    async def one(_db, _model, _project_id, row_id, _label):
        return element if row_id == "element" else page

    async def target(_environment, _page_url, _override):
        return "https://example.test/login"

    monkeypatch.setattr(ui_verification, "_one", one)
    monkeypatch.setattr(ui_verification, "require_membership", lambda *_: asyncio.sleep(0))
    monkeypatch.setattr(ui_verification, "resolve_target_url", target)
    monkeypatch.setattr(ui_verification, "enqueue_ui_actuator", lambda *args: queued.append(args))
    data = SimpleNamespace(environment_id="env", target_url=None, navigation_timeout_ms=1000,
                           operation_timeout_ms=1000, total_timeout_ms=2000)
    result = asyncio.run(ui_verification.request_element_verification(
        db, "project", SimpleNamespace(id="user"), "element", data))

    assert result["status"] == "pending"
    assert queued[0][0] == "app.ui_verification_jobs.run_verification_job"
    assert db.added[0].element_revision == 3 and db.added[0].environment_id == "env"


def test_non_unique_locator_preserves_existing_verified_state(monkeypatch):
    element = UiElement(id="element", project_id="project", page_id="page", name="login", primary_locator={"type": "css", "value": ".login"}, fallback_locators=[], revision=2, verified=True, created_by="user")
    page = UiPage(id="page", project_id="project", module_id="module", name="login", url="/login", created_by="user")
    environment = EnvironmentModel(id="env", project_id="project", name="test", base_url="https://example.test", created_by="user")
    db = FakeDb(environment)

    async def one(_db, _model, _project_id, row_id, _label):
        return element if row_id == "element" else page

    async def target(_environment, _page_url, _override):
        return "https://example.test/login"

    monkeypatch.setattr(ui_verification, "_one", one)
    monkeypatch.setattr(ui_verification, "require_membership", lambda *_: asyncio.sleep(0))
    monkeypatch.setattr(ui_verification, "resolve_target_url", target)
    result = asyncio.run(ui_verification.verify_element(db, "project", SimpleNamespace(id="user"), "element", SimpleNamespace(environment_id="env", target_url=None, navigation_timeout_ms=1000, operation_timeout_ms=1000, total_timeout_ms=1000), FakeVerifier(BrowserVerificationResult(actual_url="https://example.test/login", match_count=2, visible=True, actionable=True, dom_summary="token=never-leak"))))

    assert result["status"] == "failed"
    assert element.verified is True
    assert "never-leak" not in db.added[0].dom_summary


def test_playwright_runtime_failure_is_structured_error():
    with pytest.raises(AppError) as caught:
        asyncio.run(ui_verification.PlaywrightVerifier().verify("https://example.test", None, None, {"navigation": 100, "operation": 100, "total": 100}, Path("data/test.png")))
    assert caught.value.code in {"UI_PLAYWRIGHT_UNAVAILABLE", "UI_VERIFICATION_TIMEOUT", "UI_BROWSER_ERROR"}
