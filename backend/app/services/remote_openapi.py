from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.config import Settings, get_settings
from app.errors import AppError
from app.schemas.assets import OpenApiImportAuth

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 3
Resolver = Callable[[str, int], Awaitable[set[ipaddress.IPv4Address | ipaddress.IPv6Address]]]


def sanitized_source_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    try:
        parsed_port = parts.port
    except ValueError as exc:
        raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 端口无效", 422) from exc
    port = f":{parsed_port}" if parsed_port else ""
    return urlunsplit((parts.scheme.lower(), f"{host}{port}", parts.path or "/", "", ""))


def _host_is_allowed(host: str, allowed_hosts: set[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(
        host == entry or (entry.startswith("*.") and host.endswith(entry[1:]) and host != entry[2:])
        for entry in allowed_hosts
    )


def _is_forbidden_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


async def resolve_host_addresses(host: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        return {ipaddress.ip_address(host)}
    except ValueError:
        pass

    try:
        records = await asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AppError("REMOTE_OPENAPI_DNS_FAILED", "OpenAPI URL 域名解析失败", 422) from exc
    return {ipaddress.ip_address(record[4][0]) for record in records}


async def validate_remote_url(url: str, settings: Settings, resolver: Resolver = resolve_host_addresses) -> str:
    value = url.strip()
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 仅支持完整的 HTTP/HTTPS 地址", 422)
    if parts.username or parts.password or parts.fragment:
        raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 不能包含用户信息或片段", 422)
    try:
        parsed_port = parts.port
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError) as exc:
        raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 域名或端口无效", 422) from exc
    if not _host_is_allowed(host, settings.allowed_remote_hosts):
        raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 域名不在允许名单中", 403, {"host": host})
    addresses = await asyncio.wait_for(
        resolver(host, parsed_port or (443 if parts.scheme.lower() == "https" else 80)),
        timeout=settings.remote_openapi_timeout_seconds,
    )
    if not addresses or any(_is_forbidden_address(address) for address in addresses):
        raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 解析到内网、回环或保留地址", 403, {"host": host})
    return value


def _auth_headers(auth: OpenApiImportAuth) -> tuple[dict[str, str], set[str]]:
    headers = {
        "Accept": "application/json, application/yaml, text/yaml, text/plain",
        "User-Agent": "ai-test/openapi-import",
    }
    sensitive: set[str] = set()
    if auth.type == "basic":
        encoded = base64.b64encode(f"{auth.username}:{auth.password}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
        sensitive.add("authorization")
    elif auth.type == "bearer":
        headers["Authorization"] = f"Bearer {auth.token}"
        sensitive.add("authorization")
    elif auth.type == "header":
        headers[str(auth.header_name)] = str(auth.header_value)
        sensitive.add(str(auth.header_name).lower())
    return headers, sensitive


def _origin(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or (443 if parts.scheme == "https" else 80)


async def fetch_remote_openapi(
    url: str,
    auth: OpenApiImportAuth,
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver = resolve_host_addresses,
) -> tuple[bytes, str]:
    config = settings or get_settings()
    if not config.remote_openapi_enabled:
        raise AppError("REMOTE_OPENAPI_DISABLED", "远程 OpenAPI 导入未启用，请配置允许域名后重试", 403)
    if not config.allowed_remote_hosts:
        raise AppError("REMOTE_OPENAPI_ALLOWLIST_EMPTY", "远程 OpenAPI 允许域名列表为空", 403)

    try:
        async with asyncio.timeout(config.remote_openapi_timeout_seconds):
            current_url = await validate_remote_url(url, config, resolver)
            initial_origin = _origin(current_url)
            base_headers, sensitive_headers = _auth_headers(auth)
            timeout = httpx.Timeout(config.remote_openapi_timeout_seconds)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            ) as client:
                for redirect_count in range(MAX_REDIRECTS + 1):
                    request_headers = dict(base_headers)
                    if _origin(current_url) != initial_origin:
                        request_headers = {
                            key: value for key, value in request_headers.items() if key.lower() not in sensitive_headers
                        }
                    async with client.stream("GET", current_url, headers=request_headers) as response:
                        if response.status_code in REDIRECT_STATUSES:
                            if redirect_count == MAX_REDIRECTS:
                                raise AppError("REMOTE_OPENAPI_REDIRECT_LIMIT", "OpenAPI URL 重定向次数超过限制", 422)
                            location = response.headers.get("location")
                            if not location:
                                raise AppError("REMOTE_OPENAPI_FETCH_FAILED", "OpenAPI URL 返回了无目标的重定向", 502)
                            next_url = urljoin(current_url, location)
                            if urlsplit(current_url).scheme == "https" and urlsplit(next_url).scheme == "http":
                                raise AppError("REMOTE_URL_FORBIDDEN", "OpenAPI URL 不允许从 HTTPS 降级重定向到 HTTP", 403)
                            current_url = await validate_remote_url(next_url, config, resolver)
                            continue
                        if response.status_code >= 400:
                            raise AppError(
                                "REMOTE_OPENAPI_FETCH_FAILED",
                                f"远程 OpenAPI 服务返回 HTTP {response.status_code}",
                                502,
                            )
                        content_length = response.headers.get("content-length")
                        try:
                            declared_size = int(content_length) if content_length else None
                        except ValueError:
                            declared_size = None
                        if declared_size is not None and declared_size > config.remote_openapi_max_bytes:
                            raise AppError("REMOTE_OPENAPI_TOO_LARGE", "远程 OpenAPI 文档超过大小限制", 413)
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > config.remote_openapi_max_bytes:
                                raise AppError("REMOTE_OPENAPI_TOO_LARGE", "远程 OpenAPI 文档超过大小限制", 413)
                            chunks.append(chunk)
                        return b"".join(chunks), sanitized_source_url(current_url)
    except AppError:
        raise
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise AppError("REMOTE_OPENAPI_TIMEOUT", "拉取远程 OpenAPI 文档超时", 504) from exc
    except httpx.RequestError as exc:
        raise AppError("REMOTE_OPENAPI_FETCH_FAILED", "拉取远程 OpenAPI 文档失败", 502, {"type": type(exc).__name__}) from exc

    raise AppError("REMOTE_OPENAPI_FETCH_FAILED", "拉取远程 OpenAPI 文档失败", 502)
