from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MASK = "******"
SENSITIVE_HINTS = ("authorization", "cookie", "token", "secret", "password", "passwd", "pwd", "api_key", "apikey", "credential", "session", "id_card", "phone", "email")


def is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9_]", "_", key.lower())
    return any(hint in normalized for hint in SENSITIVE_HINTS)


def mask_data(value, key: str = "", known_secrets: set[str] | None = None):
    secrets = known_secrets or set()
    if key and is_sensitive_key(key) and value is not None:
        return MASK
    if isinstance(value, dict):
        result = {str(k): mask_data(v, str(k), secrets) for k, v in value.items()}
        label = value.get("key") or value.get("name")
        if label is not None and "value" in value and is_sensitive_key(str(label)):
            result["value"] = MASK
        return result
    if isinstance(value, list):
        return [mask_data(item, key, secrets) for item in value]
    if value is None:
        return None
    if is_sensitive_key(key):
        return MASK
    if isinstance(value, str):
        result = value
        for secret in sorted(secrets, key=len, reverse=True):
            if secret:
                result = result.replace(secret, MASK)
        return result
    return value


def mask_url(url: str, known_secrets: set[str] | None = None) -> str:
    parts = urlsplit(url)
    query = [(key, MASK if is_sensitive_key(key) else mask_data(value, known_secrets=known_secrets)) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
