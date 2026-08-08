import httpx
import pytest

from app.clients.errors import UpstreamNotFoundError, UpstreamProtocolError
from app.clients.stock_platform import StockPlatformClient


@pytest.mark.asyncio
async def test_composes_company_snapshot(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/valuations/DEMO":
            return httpx.Response(
                200, json={"symbol": "DEMO", "engineVersion": "v1", "scenarios": []}
            )
        if request.url.path == "/api/portfolio/export/v2":
            return httpx.Response(
                200, json={"holdings": [{"symbol": "DEMO", "computed": {"weightPct": 5}}]}
            )
        return httpx.Response(404)

    client = StockPlatformClient(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://stock.test"),
    )
    snapshot = await client.get_company_snapshot("demo")
    assert snapshot.symbol == "DEMO"
    assert snapshot.holding == {"symbol": "DEMO", "computed": {"weightPct": 5}}


@pytest.mark.asyncio
async def test_maps_not_found(settings) -> None:
    client = StockPlatformClient(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(404)),
            base_url="http://stock.test",
        ),
    )
    with pytest.raises(UpstreamNotFoundError):
        await client.get_current_valuation("DEMO")


@pytest.mark.asyncio
async def test_rejects_invalid_contract(settings) -> None:
    client = StockPlatformClient(
        settings,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"symbol": "DEMO"})),
            base_url="http://stock.test",
        ),
    )
    with pytest.raises(UpstreamProtocolError):
        await client.get_current_valuation("DEMO")
