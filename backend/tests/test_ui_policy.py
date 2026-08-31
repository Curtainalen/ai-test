import pytest

from app.errors import AppError
from app.services.ui_policy import check_action


BASE = {"current_url": "https://example.com/login", "element_keys": {"login_submit"},
        "allowed_operations": {"click", "fill", "navigate"}, "blocked_operations": {"evaluate"},
        "allowed_paths": ["/login", "/dashboard"]}


def test_action_policy_requires_real_snapshot_element_and_secret_reference_for_sensitive_input():
    with pytest.raises(AppError) as exc:
        check_action(action={"operation": "click", "target_element_key": "made-up"}, **BASE)
    assert exc.value.code == "UI_EXPLORATION_ELEMENT_INVALID"
    result = check_action(action={"operation": "fill", "target_element_key": "login_submit", "value": "search text"},
                          element_label="搜索", **BASE)
    assert result["allowed"] is True
    with pytest.raises(AppError) as exc:
        check_action(action={"operation": "fill", "target_element_key": "login_submit", "value": "plaintext"},
                     element_label="密码", **BASE)
    assert exc.value.code == "UI_SENSITIVE_INPUT_REFERENCE_REQUIRED"


def test_action_policy_blocks_cross_origin_and_flags_dangerous_actions():
    with pytest.raises(AppError) as exc:
        check_action(action={"operation": "navigate", "value": "https://evil.example/x"}, **BASE)
    assert exc.value.code == "UI_TARGET_URL_FORBIDDEN"
    result = check_action(action={"operation": "click", "target_element_key": "login_submit", "reason": "删除订单"},
                          element_label="删除", **BASE)
    assert result["requires_approval"] is True
