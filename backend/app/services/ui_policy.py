from urllib.parse import urljoin, urlsplit

from app.errors import AppError

DANGEROUS_WORDS = ("delete", "remove", "pay", "purchase", "send", "submit order", "删除", "支付", "付款", "发信", "提交订单")
SENSITIVE_INPUT_WORDS = (
    "password", "passwd", "passcode", "token", "secret", "cookie", "authorization",
    "api key", "apikey", "credit card", "card number", "cvv", "身份证", "密码", "口令",
    "令牌", "密钥", "银行卡", "信用卡", "手机号", "手机号码", "邮箱", "电子邮件",
)
ELEMENT_OPERATIONS = {"click", "fill", "select", "hover", "press", "check", "uncheck", "assert_visible", "assert_text"}


def check_action(*, action: dict, current_url: str, element_keys: set[str], allowed_operations: set[str],
                 blocked_operations: set[str], allowed_paths: list[str], element_label: str = "") -> dict:
    operation = str(action.get("operation") or "")
    if operation not in allowed_operations or operation in blocked_operations:
        raise AppError("UI_EXPLORATION_OPERATION_FORBIDDEN", "探索动作不在白名单内", 422)
    key = action.get("target_element_key")
    if operation in ELEMENT_OPERATIONS and key not in element_keys:
        raise AppError("UI_EXPLORATION_ELEMENT_INVALID", "目标元素不属于当前 snapshot", 422)
    value = str(action.get("value") or "")
    input_context = f"{element_label} {key or ''} {action.get('reason', '')}".lower()
    if operation == "fill" and value and any(word in input_context for word in SENSITIVE_INPUT_WORDS) and not value.startswith("secret://"):
        raise AppError("UI_SENSITIVE_INPUT_REFERENCE_REQUIRED", "输入值必须使用 secret:// 引用", 422)
    if operation == "navigate":
        target = urljoin(current_url, value); current, proposed = urlsplit(current_url), urlsplit(target)
        if (current.scheme, current.hostname, current.port) != (proposed.scheme, proposed.hostname, proposed.port):
            raise AppError("UI_TARGET_URL_FORBIDDEN", "探索导航超出允许域名", 403)
        path = proposed.path or "/"
        if allowed_paths and not any(path == item or path.startswith(item.rstrip("/") + "/") for item in allowed_paths):
            raise AppError("UI_PATH_FORBIDDEN", "探索导航超出允许路径", 403)
    text = f"{element_label} {action.get('reason', '')}".lower()
    needs_approval = operation in {"click", "press", "check", "select"} and any(word in text for word in DANGEROUS_WORDS)
    return {"allowed": not needs_approval, "requires_approval": needs_approval,
            "code": "UI_DANGEROUS_ACTION_APPROVAL_REQUIRED" if needs_approval else None}
