import json

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


@pytest.mark.asyncio
async def test_readiness_uses_existing_openapi_endpoint(settings) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, json={"openapi": "3.0.1"})

    client = StockPlatformClient(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://stock.test"),
    )
    assert await client.readiness()
    assert requested == ["/v3/api-docs"]


@pytest.mark.asyncio
async def test_omits_optional_assumptions_from_default_scenario(settings) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "symbol": "DEMO",
                "engineVersion": "v1",
                "scenario": {"scenarioType": "BASE", "valid": True},
            },
        )

    client = StockPlatformClient(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://stock.test"),
    )
    await client.run_valuation_scenario("DEMO", "BASE")
    assert payloads == [{"scenarioType": "BASE"}]


@pytest.mark.asyncio
async def test_reverse_dcf_reuses_saved_base_assumptions(settings) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/valuations/DEMO" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "symbol": "DEMO",
                    "engineVersion": "v1",
                    "scenarios": [
                        {
                            "scenarioType": "BASE",
                            "valid": True,
                            "resolvedAssumptions": {"initialGrowthRatePct": 7},
                        }
                    ],
                },
            )
        if request.url.path == "/api/valuations/DEMO/evaluate":
            payloads.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "symbol": "DEMO",
                    "engineVersion": "v1",
                    "scenario": {"scenarioType": "BASE", "valid": True},
                    "reverseDcf": {"status": "AVAILABLE"},
                },
            )
        return httpx.Response(404)

    client = StockPlatformClient(
        settings,
        httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://stock.test"),
    )
    assert await client.solve_market_implied_assumptions("DEMO") == {"status": "AVAILABLE"}
    assert payloads == [{"scenarioType": "BASE", "assumptions": {"initialGrowthRatePct": 7}}]
