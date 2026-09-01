from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
import json

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


def _parse_json_content(content: str):
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


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
    summary = f"HTTP {response.status_code}"
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("error") or body.get("message") or body.get("error_message")
            if isinstance(detail, dict): detail = detail.get("message") or detail.get("code")
            if detail: summary = f"HTTP {response.status_code}: {str(detail)[:500]}"
    except (ValueError, json.JSONDecodeError):
        pass
    return {
        "ok": False,
        "latency_ms": latency_ms,
        "model": config.model_name,
        "error_class": classify_status(response.status_code),
        "upstream_status": response.status_code,
        "upstream_summary": summary,
    }


async def test_structured_output(config, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Call the configured endpoint and verify that it returns the expected JSON object."""
    request = build_probe_request(config, api_key)
    mode = str((config.extra_params or {}).get("structured_output_mode") or "json_object")
    payload = dict(request.payload)
    if config.protocol == OPENAI_CHAT:
        payload["max_tokens"] = 128
        payload["messages"] = [{"role": "user", "content": "Return exactly this JSON object: {\"ok\":true}"}]
        if mode == "json_schema":
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "probe", "strict": True, "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}}}
        else:
            payload["response_format"] = {"type": "json_object"}
    elif config.protocol == ANTHROPIC:
        payload["max_tokens"] = 128
        payload["messages"] = [{"role": "user", "content": "Return only this valid JSON object, with no Markdown or explanation: {\"ok\":true}"}]
    started = time.perf_counter()
    try:
        timeout = httpx.Timeout(float(config.timeout_seconds))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
            response = await client.post(request.url, headers=request.headers, json=payload)
    except httpx.TimeoutException:
        return {"ok": False, "model": config.model_name, "error_class": "TIMEOUT", "latency_ms": int((time.perf_counter() - started) * 1000)}
    except httpx.RequestError:
        return {"ok": False, "model": config.model_name, "error_class": "NETWORK", "latency_ms": int((time.perf_counter() - started) * 1000)}
    latency = int((time.perf_counter() - started) * 1000)
    if not 200 <= response.status_code < 300:
        result = await probe_config(config, api_key, transport=transport)
        result["latency_ms"] = latency
        return result
    try:
        body = response.json()
        if config.protocol == OPENAI_CHAT:
            content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        elif config.protocol == ANTHROPIC:
            content = "".join(str(item.get("text") or "") for item in body.get("content") or [])
        else:
            content = ((body.get("candidates") or [{}])[0].get("content") or {}).get("parts", [{}])[0].get("text", "")
        parsed = _parse_json_content(content)
        if not isinstance(parsed, dict) or parsed.get("ok") is not True:
            return {"ok": False, "model": config.model_name, "error_class": "INVALID_JSON", "upstream_summary": "模型返回的内容不是预期 JSON 对象", "latency_ms": latency}
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
        preview = str(content or "").replace("\n", " ").strip()[:240] if 'content' in locals() else "空响应"
        return {"ok": False, "model": config.model_name, "error_class": "INVALID_JSON", "upstream_summary": f"模型返回的内容无法解析为 JSON，响应摘要：{preview or '空响应'}", "latency_ms": latency}
    return {"ok": True, "model": config.model_name, "error_class": None, "latency_ms": latency, "structured_output_mode": mode}
