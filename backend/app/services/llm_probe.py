from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.errors import AppError

OPENAI_CHAT = "openai_chat"
ANTHROPIC = "anthropic"
GEMINI = "gemini"
SUPPORTED_PROTOCOLS = frozenset({OPENAI_CHAT, ANTHROPIC, GEMINI})
DEFAULT_BASE_URLS = {
    OPENAI_CHAT: "https://api.openai.com/v1",
    ANTHROPIC: "https://api.anthropic.com/v1",
    GEMINI: "https://generativelanguage.googleapis.com/v1beta",
}


@dataclass(frozen=True)
class ProbeRequest:
    url: str
    headers: dict[str, str]
    payload: dict


def validate_protocol(protocol: str) -> str:
    if protocol not in SUPPORTED_PROTOCOLS:
        raise AppError("MODEL_PROTOCOL_UNSUPPORTED", "暂不支持该模型协议", 422)
    return protocol


def build_probe_request(config, api_key: str) -> ProbeRequest:
    protocol = validate_protocol(str(config.protocol))
    base_url = str(config.base_url or DEFAULT_BASE_URLS[protocol]).rstrip("/")
    model_name = str(config.model_name)
    if protocol == OPENAI_CHAT:
        return ProbeRequest(
            url=f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"},
            payload={"model": model_name, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1, "stream": False},
        )
    if protocol == ANTHROPIC:
        version = str((config.extra_params or {}).get("api_version") or "2023-06-01")
        headers = {"anthropic-version": version, "content-type": "application/json"}
        if api_key:
            headers["x-api-key"] = api_key
        return ProbeRequest(
            url=f"{base_url}/messages",
            headers=headers,
            payload={"model": model_name, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
        )
    headers = {"content-type": "application/json"}
    if api_key:
        headers["x-goog-api-key"] = api_key
    return ProbeRequest(
        url=f"{base_url}/models/{model_name}:generateContent",
        headers=headers,
        payload={"contents": [{"role": "user", "parts": [{"text": "ping"}]}], "generationConfig": {"maxOutputTokens": 1}},
    )


def classify_status(status_code: int) -> str:
    if status_code in {401, 403}:
        return "AUTH_FAILED"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 429:
        return "RATE_LIMITED"
    if 500 <= status_code <= 599:
        return "UPSTREAM_ERROR"
    return "UNKNOWN"


async def probe_config(config, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Send one minimal request. Never return upstream bodies, URLs, or headers."""
    request = build_probe_request(config, api_key)
    started = time.perf_counter()
    try:
        timeout = httpx.Timeout(float(config.timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
            response = await client.post(request.url, headers=request.headers, json=request.payload)
    except httpx.TimeoutException:
        return {"ok": False, "latency_ms": int((time.perf_counter() - started) * 1000), "model": config.model_name, "error_class": "TIMEOUT"}
    except httpx.RequestError:
        return {"ok": False, "latency_ms": int((time.perf_counter() - started) * 1000), "model": config.model_name, "error_class": "NETWORK"}
    latency_ms = int((time.perf_counter() - started) * 1000)
    if 200 <= response.status_code < 300:
        return {"ok": True, "latency_ms": latency_ms, "model": config.model_name, "error_class": None}
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "model": config.model_name,
        "error_class": classify_status(response.status_code),
        "upstream_status": response.status_code,
        "upstream_summary": f"HTTP {response.status_code}",
    }
