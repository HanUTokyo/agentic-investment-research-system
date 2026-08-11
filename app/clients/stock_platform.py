import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.clients.errors import (
    UpstreamNotFoundError,
    UpstreamProtocolError,
    UpstreamServiceError,
    UpstreamTimeoutError,
)
from app.config import Settings
from app.contracts import CompanySnapshot, FinancialHistory, ValuationEvaluation, ValuationSnapshot


class StockPlatformClient:
    """Read-only HTTP adapter for the authoritative Java investment platform."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        headers = {"Accept": "application/json"}
        if settings.stock_platform_api_token:
            headers["Authorization"] = f"Bearer {settings.stock_platform_api_token}"
        self._client = client or httpx.AsyncClient(
            base_url=str(settings.stock_platform_base_url).rstrip("/"),
            headers=headers,
            timeout=settings.http_timeout_seconds,
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def readiness(self) -> bool:
        try:
            # The Java platform publishes OpenAPI but does not depend on Spring Actuator.
            response = await self._client.get("/v3/api-docs")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def get_current_valuation(self, symbol: str) -> ValuationSnapshot:
        payload = await self._read_json(f"/api/valuations/{self._symbol(symbol)}")
        return self._parse(ValuationSnapshot, payload)

    async def get_financial_history(self, symbol: str) -> FinancialHistory:
        normalized = self._symbol(symbol)
        fundamentals = await self._read_json(
            "/api/portfolio/history/fundamentals", {"symbol": normalized}
        )
        allocation = await self._read_json(
            "/api/portfolio/history/capital-allocation", {"symbol": normalized}
        )
        return FinancialHistory(
            symbol=normalized, quarterly_fundamentals=fundamentals, capital_allocation=allocation
        )

    async def get_company_snapshot(self, symbol: str) -> CompanySnapshot:
        normalized = self._symbol(symbol)
        valuation, export = await asyncio.gather(
            self.get_current_valuation(normalized), self._read_json("/api/portfolio/export/v2")
        )
        holdings = export.get("holdings", []) if isinstance(export, dict) else []
        holding = next(
            (item for item in holdings if item.get("symbol", "").upper() == normalized), None
        )
        return CompanySnapshot(symbol=normalized, valuation=valuation, holding=holding)

    async def run_valuation_scenario(
        self, symbol: str, scenario_type: str, assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation:
        payload: dict[str, Any] = {"scenarioType": scenario_type.upper()}
        if assumptions is not None:
            payload["assumptions"] = assumptions
        result = await self._write_json(f"/api/valuations/{self._symbol(symbol)}/evaluate", payload)
        return self._parse(ValuationEvaluation, result)

    async def get_forecast_template(self, symbol: str) -> dict[str, Any]:
        """Read the Java-owned explicit-forecast template without mutating it."""
        result = await self._read_json(
            f"/api/valuations/{self._symbol(symbol)}/forecast-template"
        )
        if not isinstance(result, dict):
            raise UpstreamProtocolError("forecast template response must be an object")
        return result

    async def preview_explicit_forecast(
        self, symbol: str, *, archetype: str, scenarios: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run a bounded Java preview; only deterministic executors may provide overrides."""
        payload: dict[str, Any] = {"archetype": archetype}
        if scenarios is not None:
            payload["scenarios"] = scenarios
        result = await self._write_json(
            f"/api/valuations/{self._symbol(symbol)}/forecast-preview",
            payload,
        )
        if not isinstance(result, dict):
            raise UpstreamProtocolError("forecast preview response must be an object")
        return result

    async def solve_market_implied_assumptions(self, symbol: str) -> dict[str, Any] | None:
        # `/evaluate` does not load a persisted scenario.  Reuse the saved BASE
        # settings exposed by the read-only valuation snapshot so the reverse-DCF
        # result is based on the same Java-engine assumptions the user sees.
        snapshot = await self.get_current_valuation(symbol)
        base = next(
            (
                scenario
                for scenario in snapshot.scenarios
                if scenario.scenario_type.upper() == "BASE"
            ),
            None,
        )
        if base is None or not base.valid or base.resolved_assumptions is None:
            return None
        evaluation = await self.run_valuation_scenario(symbol, "BASE", base.resolved_assumptions)
        return evaluation.reverse_dcf

    async def _read_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        return await self._with_read_retry(lambda: self._client.get(path, params=params))

    async def _write_json(self, path: str, payload: dict[str, Any]) -> Any:
        return await self._request(lambda: self._client.post(path, json=payload))

    async def _with_read_retry(self, request: Callable[[], Awaitable[httpx.Response]]) -> Any:
        for attempt in range(2):
            try:
                return await self._request(request)
            except (UpstreamTimeoutError, UpstreamServiceError):
                if attempt:
                    raise
                await asyncio.sleep(0.1)
        raise AssertionError("unreachable")

    async def _request(self, request: Callable[[], Awaitable[httpx.Response]]) -> Any:
        try:
            response = await request()
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("stock platform request timed out") from exc
        except httpx.HTTPError as exc:
            raise UpstreamServiceError("stock platform request failed") from exc
        if response.status_code == 404:
            raise UpstreamNotFoundError("tracked symbol was not found")
        if not response.is_success:
            raise UpstreamServiceError(f"stock platform returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamProtocolError("stock platform returned invalid JSON") from exc

    @staticmethod
    def _parse(model: type[Any], payload: Any) -> Any:
        try:
            return model.model_validate(payload)
        except Exception as exc:
            raise UpstreamProtocolError(
                "stock platform response violated the checked contract"
            ) from exc

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.strip().upper()
        if not normalized or not normalized.isalnum():
            raise ValueError("symbol must be a non-empty alphanumeric ticker")
        return normalized
