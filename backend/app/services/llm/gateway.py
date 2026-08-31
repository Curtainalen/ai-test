from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import LlmCallRecord, ModelConfig, ModelConfigRevision
from app.security import decrypt_secret
from app.services.llm.schemas import LlmResult
from app.services.llm_probe import ANTHROPIC, GEMINI, OPENAI_CHAT, build_probe_request
from app.services.masking import MASK, mask_data

_limits: dict[str, asyncio.Semaphore] = {}
_limit_lock = asyncio.Lock()


class LlmGateway(Protocol):
    async def generate(self, *, project_id: str, model_config_id: str, prompt: str,
                       response_schema: dict, timeout_ms: int,
                       cancellation_token: asyncio.Event | None = None,
                       created_by: str, purpose: str = "generation") -> LlmResult: ...


def _redact_text(value: str) -> str:
    return re.sub(
        r'(?i)(password|passwd|pwd|token|authorization|cookie|secret|api[_-]?key)(\s*[:=]\s*)([^\s,;]+)',
        rf"\1\2{MASK}", value,
    )[:100_000]


def _validate_schema(value, schema: Mapping, path: str = "$") -> None:
    expected = schema.get("type")
    type_map = {"object": dict, "array": list, "string": str, "integer": int,
                "number": (int, float), "boolean": bool, "null": type(None)}
    if expected in type_map and (not isinstance(value, type_map[expected]) or expected == "integer" and isinstance(value, bool)):
        raise AppError("LLM_RESPONSE_SCHEMA_INVALID", f"结构化响应字段 {path} 类型不匹配", 502)
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                raise AppError("LLM_RESPONSE_SCHEMA_INVALID", f"结构化响应缺少字段 {path}.{name}", 502)
        properties = schema.get("properties", {})
        for name, child in properties.items():
            if name in value:
                _validate_schema(value[name], child, f"{path}.{name}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")


def _payload(config: ModelConfig, prompt: str, response_schema: dict) -> tuple[str, dict, dict]:
    base = build_probe_request(config, decrypt_secret(config.api_key_encrypted))
    if config.protocol == OPENAI_CHAT:
        body = {"model": config.model_name, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "stream": False,
                "response_format": {"type": "json_schema", "json_schema": {"name": "result", "strict": True, "schema": response_schema}}}
    elif config.protocol == ANTHROPIC:
        body = {"model": config.model_name, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    elif config.protocol == GEMINI:
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": response_schema}}
    else:
        raise AppError("MODEL_PROTOCOL_UNSUPPORTED", "暂不支持该模型协议", 422)
    return base.url, base.headers, body


def _content(payload: dict, protocol: str) -> str:
    if protocol == OPENAI_CHAT:
        choices = payload.get("choices") or []
        return str(((choices[0].get("message") or {}).get("content")) if choices else "")
    if protocol == ANTHROPIC:
        return "".join(str(item.get("text") or "") for item in payload.get("content") or [] if item.get("type") == "text")
    candidates = payload.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
    return "".join(str(item.get("text") or "") for item in parts)


def _usage(payload: dict, protocol: str) -> tuple[int | None, int | None]:
    usage = payload.get("usage") or payload.get("usageMetadata") or {}
    if protocol == GEMINI:
        return usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
    return usage.get("prompt_tokens", usage.get("input_tokens")), usage.get("completion_tokens", usage.get("output_tokens"))


async def _post_with_cancellation(client: httpx.AsyncClient, url: str, headers: dict, body: dict,
                                  cancellation_token: asyncio.Event | None) -> httpx.Response:
    request_task = asyncio.create_task(client.post(url, headers=headers, json=body))
    if cancellation_token is None:
        return await request_task
    cancellation_task = asyncio.create_task(cancellation_token.wait())
    try:
        done, _ = await asyncio.wait({request_task, cancellation_task}, return_when=asyncio.FIRST_COMPLETED)
        if cancellation_task in done and cancellation_task.result():
            request_task.cancel()
            await asyncio.gather(request_task, return_exceptions=True)
            raise AppError("LLM_CALL_CANCELED", "模型调用已取消", 409)
        return await request_task
    finally:
        cancellation_task.cancel()
        await asyncio.gather(cancellation_task, return_exceptions=True)


class DefaultLlmGateway:
    def __init__(self, db: AsyncSession, *, transport: httpx.AsyncBaseTransport | None = None, project_concurrency: int = 2):
        self.db = db
        self.transport = transport
        self.project_concurrency = project_concurrency

    async def _semaphore(self, project_id: str) -> asyncio.Semaphore:
        async with _limit_lock:
            return _limits.setdefault(project_id, asyncio.Semaphore(self.project_concurrency))

    async def _revision(self, config: ModelConfig, project_id: str, created_by: str) -> ModelConfigRevision:
        row = await self.db.scalar(select(ModelConfigRevision).where(
            ModelConfigRevision.project_id == project_id, ModelConfigRevision.model_config_id == config.id,
            ModelConfigRevision.revision == config.revision))
        if row:
            return row
        snapshot = {"provider": config.provider, "protocol": config.protocol, "model_name": config.model_name,
                    "base_url": config.base_url, "extra_params": mask_data(config.extra_params or {}),
                    "timeout_seconds": config.timeout_seconds, "max_retries": config.max_retries}
        row = ModelConfigRevision(project_id=project_id, model_config_id=config.id, revision=config.revision,
                                  config_snapshot=snapshot, api_key_encrypted=config.api_key_encrypted, created_by=created_by)
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            row = await self.db.scalar(select(ModelConfigRevision).where(
                ModelConfigRevision.project_id == project_id, ModelConfigRevision.model_config_id == config.id,
                ModelConfigRevision.revision == config.revision))
        if row is None:
            raise AppError("MODEL_CONFIG_REVISION_FAILED", "无法冻结模型配置版本", 500)
        return row

    async def generate(self, *, project_id: str, model_config_id: str, prompt: str,
                       response_schema: dict, timeout_ms: int, cancellation_token: asyncio.Event | None = None,
                       created_by: str, purpose: str = "generation") -> LlmResult:
        config = await self.db.scalar(select(ModelConfig).where(ModelConfig.id == model_config_id, ModelConfig.is_enabled.is_(True)))
        if config is None:
            raise AppError("MODEL_CONFIG_NOT_FOUND", "模型配置不存在或已停用", 404)
        revision = await self._revision(config, project_id, created_by)
        redacted_prompt = _redact_text(prompt)
        record = LlmCallRecord(project_id=project_id, model_config_id=config.id, model_config_revision_id=revision.id,
                               purpose=purpose, status="running", prompt_redacted=redacted_prompt,
                               response_schema=mask_data(response_schema), created_by=created_by)
        self.db.add(record)
        await self.db.commit()
        started = time.perf_counter()
        try:
            if cancellation_token and cancellation_token.is_set():
                raise AppError("LLM_CALL_CANCELED", "模型调用已取消", 409)
            url, headers, body = _payload(config, redacted_prompt, response_schema)
            connect = min(10.0, timeout_ms / 1000)
            read = min(float(config.timeout_seconds), timeout_ms / 1000)
            attempts = min(max(config.max_retries, 0), 2) + 1
            async with await self._semaphore(project_id):
                for attempt in range(attempts):
                    try:
                        async with asyncio.timeout(timeout_ms / 1000):
                            async with httpx.AsyncClient(timeout=httpx.Timeout(read, connect=connect), follow_redirects=False, transport=self.transport) as client:
                                response = await _post_with_cancellation(client, url, headers, body, cancellation_token)
                        if response.status_code < 500 and response.status_code != 429:
                            break
                    except httpx.TimeoutException as exc:
                        if attempt + 1 == attempts:
                            raise AppError("LLM_TIMEOUT", "模型连接或读取超时", 504) from exc
                if response.status_code >= 400:
                    code = {401: "LLM_AUTH_FAILED", 403: "LLM_AUTH_FAILED", 404: "LLM_NOT_FOUND", 429: "LLM_RATE_LIMITED"}.get(response.status_code, "LLM_UPSTREAM_ERROR")
                    raise AppError(code, f"模型服务返回 HTTP {response.status_code}", 502)
            raw = response.json()
            try:
                data = json.loads(_content(raw, config.protocol))
            except (json.JSONDecodeError, TypeError) as exc:
                raise AppError("LLM_RESPONSE_JSON_INVALID", "模型未返回有效 JSON", 502) from exc
            _validate_schema(data, response_schema)
            input_tokens, output_tokens = _usage(raw, config.protocol)
            record.status, record.response_redacted = "succeeded", mask_data(data)
            record.input_tokens, record.output_tokens = input_tokens, output_tokens
            record.usage_unknown = input_tokens is None and output_tokens is None
            return LlmResult(data, record.id, revision.id, input_tokens, output_tokens, record.usage_unknown)
        except TimeoutError as exc:
            record.status, record.error_code, record.error_message = "failed", "LLM_TIMEOUT", "模型调用总超时"
            raise AppError("LLM_TIMEOUT", "模型调用总超时", 504) from exc
        except AppError as exc:
            record.status, record.error_code, record.error_message = "canceled" if exc.code == "LLM_CALL_CANCELED" else "failed", exc.code, _redact_text(exc.message)
            raise
        except httpx.RequestError as exc:
            record.status, record.error_code, record.error_message = "failed", "LLM_NETWORK_ERROR", "模型网络请求失败"
            raise AppError("LLM_NETWORK_ERROR", "模型网络请求失败", 502) from exc
        finally:
            record.latency_ms = int((time.perf_counter() - started) * 1000)
            await self.db.commit()
