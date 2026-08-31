import httpx
import pytest

from app.errors import AppError
from app.services.http_execution import execute_request


class StreamingJson(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"data":{"user":"tester"}}'


@pytest.mark.asyncio
async def test_http_execution_extracts_asserts_and_masks_echoed_secret() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer runtime-secret"
        return httpx.Response(200, json={"data": {"access_token": "runtime-secret", "user": "tester"}}, headers={"X-Token": "runtime-secret"})

    result = await execute_request(
        {"method": "GET", "url": "https://example.test/me", "headers": {"Authorization": "Bearer runtime-secret"}, "extracts": [{"name": "access_token", "expression": "data.access_token", "sensitive": True}], "assertions": [{"type": "status_code", "expected": 200}]},
        known_secrets={"runtime-secret"},
        transport=httpx.MockTransport(handler),
    )
    assert result["status"] == "passed"
    assert "runtime-secret" not in str(result["response"])
    assert "runtime-secret" not in str(result["extracted"])
    assert result["runtime_extracted"]["access_token"] == "runtime-secret"


@pytest.mark.asyncio
async def test_http_execution_enforces_response_limit() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 2048))
    with pytest.raises(AppError) as caught:
        await execute_request({"method": "GET", "url": "https://example.test/large"}, max_response_bytes=1024, transport=transport)
    assert caught.value.code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_http_execution_parses_an_unread_streaming_json_response() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=StreamingJson(),
        )
    )

    result = await execute_request(
        {
            "method": "GET",
            "url": "https://example.test/stream",
            "assertions": [
                {"type": "json_field", "field": "data.user", "expected": "tester"}
            ],
        },
        transport=transport,
    )

    assert result["status"] == "passed"
    assert result["response"]["json"] == {"data": {"user": "tester"}}
