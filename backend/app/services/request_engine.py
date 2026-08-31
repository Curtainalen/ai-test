from __future__ import annotations

import base64
import os
import re
from copy import deepcopy
from urllib.parse import urljoin, urlsplit

from app.errors import AppError
from app.services.masking import mask_data, mask_url

VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.-]*)}|\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}")
EXACT_PATTERN = re.compile(r"^(?:\$\{([A-Za-z_][A-Za-z0-9_.-]*)}|\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\})$")


MERGED_REQUEST_FIELDS = ("path_params", "params", "headers", "cookies", "variables")


def apply_request_override(base_request: dict, request_override: dict | None) -> dict:
    """Apply scenario overrides while preserving map-shaped interface defaults."""
    merged = deepcopy(base_request)
    override = request_override or {}
    for field in MERGED_REQUEST_FIELDS:
        if field in override:
            merged[field] = {**(merged.get(field) or {}), **(override.get(field) or {})}
    if "auth" in override:
        merged["auth"] = {**(merged.get("auth") or {}), **(override.get("auth") or {})}
    for field, value in override.items():
        if field not in {*MERGED_REQUEST_FIELDS, "auth"}:
            merged[field] = deepcopy(value)
    return merged


def collect_missing(value, variables: dict, path: str = "request") -> list[dict]:
    missing: dict[str, set[str]] = {}
    def walk(item, current: str):
        if isinstance(item, str):
            for match in VAR_PATTERN.finditer(item):
                name = match.group(1) or match.group(2)
                if name not in variables:
                    missing.setdefault(name, set()).add(current)
        elif isinstance(item, dict):
            for key, child in item.items(): walk(child, f"{current}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item): walk(child, f"{current}[{index}]")
    walk(value, path)
    return [{"name": name, "paths": sorted(paths)} for name, paths in sorted(missing.items())]


def resolve_value(value, variables: dict):
    if isinstance(value, str):
        exact = EXACT_PATTERN.match(value)
        if exact: return deepcopy(variables[exact.group(1) or exact.group(2)])
        return VAR_PATTERN.sub(lambda match: str(variables[match.group(1) or match.group(2)]), value)
    if isinstance(value, dict): return {key: resolve_value(item, variables) for key, item in value.items()}
    if isinstance(value, list): return [resolve_value(item, variables) for item in value]
    return value


def resolve_secret_refs(value):
    if isinstance(value, str) and value.startswith("secret://"):
        name = re.sub(r"[^A-Za-z0-9]", "_", value[9:]).upper()
        secret = os.getenv(f"AITEST_SECRET_{name}")
        if secret is None: raise AppError("SECRET_NOT_CONFIGURED", "密钥引用未配置", 422, {"reference": value})
        return secret
    if isinstance(value, dict): return {key: resolve_secret_refs(item) for key, item in value.items()}
    if isinstance(value, list): return [resolve_secret_refs(item) for item in value]
    return value


def is_sensitive_name(name: str) -> bool:
    return any(hint in name.lower() for hint in ("token", "secret", "password", "passwd", "pwd", "cookie", "authorization", "api_key", "apikey", "credential"))


def collect_sensitive_values(value, key: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for child_key, child in value.items(): found |= collect_sensitive_values(child, str(child_key))
    elif isinstance(value, list):
        for child in value: found |= collect_sensitive_values(child, key)
    elif is_sensitive_name(key) and value not in (None, ""):
        found.add(str(value))
    return found


def collect_secret_ref_values(before, after) -> set[str]:
    found: set[str] = set()
    if isinstance(before, str) and before.startswith("secret://") and after not in (None, ""):
        found.add(str(after))
    elif isinstance(before, dict) and isinstance(after, dict):
        for key, child in before.items(): found |= collect_secret_ref_values(child, after.get(key))
    elif isinstance(before, list) and isinstance(after, list):
        for left, right in zip(before, after): found |= collect_secret_ref_values(left, right)
    return found


def compose_request(request: dict, environment: dict, scopes: list[dict] | None = None) -> dict:
    variables: dict = {}
    variables.update(environment.get("variables") or {})
    variables.update(request.get("variables") or {})
    for scope in scopes or []: variables.update(scope or {})
    merged = deepcopy(request)
    merged["headers"] = {**(environment.get("global_headers") or {}), **(merged.get("headers") or {})}
    raw_url = str(merged.get("url") or "")
    if urlsplit(raw_url).scheme:
        base, target = urlsplit(environment["base_url"]), urlsplit(raw_url)
        if (base.scheme.lower(), base.hostname, base.port) != (target.scheme.lower(), target.hostname, target.port):
            raise AppError("TARGET_URL_FORBIDDEN", "请求目标必须属于所选项目环境", 422)
    else:
        raw_url = urljoin(environment["base_url"].rstrip("/") + "/", raw_url.lstrip("/"))
    path_params = merged.pop("path_params", {}) or {}
    for name, value in path_params.items():
        raw_url = raw_url.replace("{" + str(name) + "}", str(value))
    merged["url"] = raw_url
    auth = merged.pop("auth", None) or {}
    if auth.get("type") == "bearer": merged["headers"]["Authorization"] = f"Bearer {auth.get('token', '')}"
    elif auth.get("type") == "basic":
        raw = f"{auth.get('username', '')}:{auth.get('password', '')}".encode()
        merged["headers"]["Authorization"] = "Basic " + base64.b64encode(raw).decode()
    elif auth.get("type") == "api_key":
        target = merged.setdefault("params", {}) if auth.get("in") == "query" else merged["headers"]
        target[str(auth.get("key") or "X-API-Key")] = auth.get("value", "")
    missing = collect_missing(merged, variables)
    if missing: raise AppError("VARIABLE_MISSING", "请求包含未定义变量", 422, {"variables": missing})
    with_variables = resolve_value(merged, variables)
    resolved = resolve_secret_refs(with_variables)
    known = {str(value) for key, value in variables.items() if is_sensitive_name(key) and value not in (None, "")}
    known |= collect_sensitive_values(resolved)
    known |= collect_secret_ref_values(with_variables, resolved)
    preview = mask_data(resolved, known_secrets=known)
    preview["url"] = mask_url(str(resolved["url"]), known)
    return {"request": resolved, "preview": preview, "variables": variables, "sensitive_values": known}


def evaluate_assertions(response: dict, assertions: list[dict]) -> list[dict]:
    results = []
    for rule in assertions:
        kind, expected = rule.get("type"), rule.get("expected")
        actual = None
        if kind == "status_code": actual = response.get("status_code")
        elif kind == "header": actual = (response.get("headers") or {}).get(rule.get("field"))
        elif kind == "text_contains": actual = str(rule.get("expected")) in str(response.get("text") or "")
        elif kind == "json_field":
            actual = response.get("json")
            for part in str(rule.get("field") or "").split("."):
                actual = actual.get(part) if isinstance(actual, dict) else None
        passed = actual is True if kind == "text_contains" else actual == expected
        results.append({**rule, "actual": actual, "passed": passed})
    return results
