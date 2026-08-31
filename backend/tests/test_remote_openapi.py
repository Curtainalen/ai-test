import asyncio
import ipaddress
import logging

import httpx
import pytest

from app.config import Settings
from app.errors import AppError
from app.logging import configure_logging
from app.schemas.assets import OpenApiImportAuth
from app.services.remote_openapi import fetch_remote_openapi, sanitized_source_url, validate_remote_url


def remote_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "x" * 32,
        "database_url": "postgresql+asyncpg://test:test@localhost/test",
        "remote_openapi_enabled": True,
        "remote_openapi_allowed_hosts": "docs.example.com,cdn.example.com",
        "remote_openapi_max_bytes": 1024,
    }
    values.update(overrides)
    return Settings(**values)


async def public_resolver(host: str, port: int):
    return {ipaddress.ip_address("93.184.216.34")}


async def redirect_resolver(host: str, port: int):
    if host == "127.0.0.1":
        return {ipaddress.ip_address("127.0.0.1")}
    return await public_resolver(host, port)


@pytest.mark.asyncio
async def test_fetch_remote_openapi_supports_bearer_and_sanitizes_source_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fetch-secret"
        return httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})

    content, source_url = await fetch_remote_openapi(
        "https://docs.example.com/openapi.json?signature=secret",
        OpenApiImportAuth(type="bearer", token="fetch-secret"),
        settings=remote_settings(),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    assert b'"openapi":"3.1.0"' in content
    assert source_url == "https://docs.example.com/openapi.json"
    assert "secret" not in source_url


@pytest.mark.asyncio
async def test_cross_origin_redirect_does_not_forward_credentials() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "docs.example.com":
            assert request.headers["authorization"] == "Bearer fetch-secret"
            return httpx.Response(302, headers={"Location": "https://cdn.example.com/openapi.json"})
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})

    await fetch_remote_openapi(
        "https://docs.example.com/openapi.json",
        OpenApiImportAuth(type="bearer", token="fetch-secret"),
        settings=remote_settings(),
        transport=httpx.MockTransport(handler),
        resolver=public_resolver,
    )

    assert len(requests) == 2


@pytest.mark.asyncio
async def test_redirect_target_is_revalidated_and_private_addresses_are_blocked() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(302, headers={"Location": "http://127.0.0.1/openapi.json"})
    )

    with pytest.raises(AppError) as caught:
        await fetch_remote_openapi(
            "http://docs.example.com/openapi.json",
            OpenApiImportAuth(),
            settings=remote_settings(remote_openapi_allowed_hosts="docs.example.com,127.0.0.1"),
            transport=transport,
            resolver=redirect_resolver,
        )

    assert caught.value.code == "REMOTE_URL_FORBIDDEN"


@pytest.mark.asyncio
async def test_remote_openapi_rejects_hosts_outside_allowlist() -> None:
    with pytest.raises(AppError) as caught:
        await validate_remote_url("https://untrusted.example/openapi.json", remote_settings(), public_resolver)
    assert caught.value.code == "REMOTE_URL_FORBIDDEN"


@pytest.mark.asyncio
async def test_remote_openapi_rejects_invalid_ports_as_structured_error() -> None:
    with pytest.raises(AppError) as caught:
        await validate_remote_url("https://docs.example.com:not-a-port/openapi.json", remote_settings(), public_resolver)
    assert caught.value.code == "REMOTE_URL_FORBIDDEN"


@pytest.mark.asyncio
async def test_remote_openapi_enforces_streamed_size_limit() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 2048))
    with pytest.raises(AppError) as caught:
        await fetch_remote_openapi(
            "https://docs.example.com/openapi.json",
            OpenApiImportAuth(),
            settings=remote_settings(),
            transport=transport,
            resolver=public_resolver,
        )
    assert caught.value.code == "REMOTE_OPENAPI_TOO_LARGE"


@pytest.mark.asyncio
async def test_remote_openapi_enforces_total_timeout() -> None:
    async def slow_handler(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})

    with pytest.raises(AppError) as caught:
        await fetch_remote_openapi(
            "https://docs.example.com/openapi.json",
            OpenApiImportAuth(),
            settings=remote_settings(remote_openapi_timeout_seconds=0.01),
            transport=httpx.MockTransport(slow_handler),
            resolver=public_resolver,
        )
    assert caught.value.code == "REMOTE_OPENAPI_TIMEOUT"


def test_http_client_request_urls_are_not_logged_at_info() -> None:
    configure_logging("INFO")
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING


def test_sanitized_source_url_removes_query_and_userinfo() -> None:
    assert sanitized_source_url("HTTPS://User:Pass@Docs.Example.com:8443/spec?token=x#part") == (
        "https://docs.example.com:8443/spec"
    )
