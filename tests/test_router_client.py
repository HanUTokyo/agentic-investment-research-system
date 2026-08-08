import httpx
import pytest

from app.clients.ai_router import RouterClient
from app.clients.errors import UpstreamServiceError, UpstreamTimeoutError


@pytest.mark.asyncio
async def test_router_completion(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}], "model": "gemma4:e4b"}
        )

    client = RouterClient(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://router.test"),
    )
    result = await client.complete([{"role": "user", "content": "hello"}])
    assert result.content == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 502, 503, 504])
async def test_router_maps_status_errors(settings, status: int) -> None:
    client = RouterClient(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status)),
            base_url="http://router.test",
        ),
    )
    with pytest.raises(UpstreamServiceError):
        await client.route("hello")


@pytest.mark.asyncio
async def test_router_timeout(settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    client = RouterClient(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://router.test"),
    )
    with pytest.raises(UpstreamTimeoutError):
        await client.route("hello")
