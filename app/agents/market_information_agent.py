"""Phase 2B specialist: bounded external market evidence, never case orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class MarketInformationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    question: str = Field(min_length=1)
    information_need: str = Field(min_length=1, max_length=600)
    relevant_context: dict[str, str] = Field(default_factory=dict)


class MarketInformationFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim: str
    value: Decimal
    source_path: str
    source_url: str
    retrieved_at: datetime
    provenance: dict[str, str] = Field(default_factory=dict)


class MarketInformationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    findings: tuple[str, ...]
    facts: tuple[MarketInformationFact, ...]
    limitations: tuple[str, ...]
    source: str
    specialist_latency_ms: float


class MarketInformationError(ValueError):
    pass


class MarketInformationAgent:
    """Retrieve one bounded external observation without owning case orchestration.

    The default is Yahoo's 52-week range.  A request explicitly asking for an
    official operating/revenue observation uses SEC company facts, preserving a
    first-party filing provenance path needed by the Phase 2C acceptance.
    """

    _URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    _SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    _SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def collect(self, request: MarketInformationRequest) -> MarketInformationResult:
        started = datetime.now(UTC)
        if self._needs_operating_observation(request.information_need):
            return await self._collect_sec_revenue(request, started)
        url = self._URL.format(symbol=request.symbol.upper())
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._client is None
        try:
            response = await client.get(url, headers={"User-Agent": "agentic-investment-research-system/0.1"})
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketInformationError(f"market source retrieval failed: {type(exc).__name__}") from exc
        finally:
            if owned_client:
                await client.aclose()
        try:
            result = payload["chart"]["result"][0]
            high = Decimal(str(result["meta"]["fiftyTwoWeekHigh"]))
            low = Decimal(str(result["meta"]["fiftyTwoWeekLow"]))
        except (KeyError, IndexError, TypeError, ArithmeticError) as exc:
            raise MarketInformationError("market source response lacks 52-week range") from exc
        retrieved_at = datetime.now(UTC)
        facts = (
            MarketInformationFact(claim=f"{request.symbol.upper()} 52-week high", value=high, source_path="chart.result[0].meta.fiftyTwoWeekHigh", source_url=url, retrieved_at=retrieved_at),
            MarketInformationFact(claim=f"{request.symbol.upper()} 52-week low", value=low, source_path="chart.result[0].meta.fiftyTwoWeekLow", source_url=url, retrieved_at=retrieved_at),
        )
        return MarketInformationResult(
            findings=("A dated external 52-week trading range is now available for reassessment.",),
            facts=facts,
            limitations=(
                "This bounded source provides a price observation only; it does not establish market expectations or causation.",
            ),
            source="Yahoo Finance chart API",
            specialist_latency_ms=(retrieved_at - started).total_seconds() * 1000,
        )

    @staticmethod
    def _needs_operating_observation(information_need: str) -> bool:
        need = information_need.lower()
        return any(
            marker in need
            for marker in (
                "official operating",
                "operating revenue",
                "official revenue",
                "reported revenue",
                "revenue guidance",
                "operating outlook",
            )
        )

    async def _collect_sec_revenue(
        self, request: MarketInformationRequest, started: datetime
    ) -> MarketInformationResult:
        client = self._client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._client is None
        headers = {"User-Agent": "agentic-investment-research-system/0.1 research@example.invalid"}
        try:
            tickers_response = await client.get(self._SEC_TICKERS_URL, headers=headers)
            tickers_response.raise_for_status()
            tickers: dict[str, Any] = tickers_response.json()
            ticker = request.symbol.upper()
            row = next(
                (item for item in tickers.values() if item.get("ticker", "").upper() == ticker), None
            )
            if not isinstance(row, dict) or not isinstance(row.get("cik_str"), int):
                raise MarketInformationError("SEC ticker mapping is unavailable")
            facts_url = self._SEC_FACTS_URL.format(cik=row["cik_str"])
            facts_response = await client.get(facts_url, headers=headers)
            facts_response.raise_for_status()
            payload: dict[str, Any] = facts_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketInformationError(f"SEC operating evidence retrieval failed: {type(exc).__name__}") from exc
        finally:
            if owned_client:
                await client.aclose()
        try:
            units = payload["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
            observations = [
                item
                for item in units
                if item.get("form") in {"10-Q", "10-K"}
                and item.get("fp") in {"Q1", "Q2", "Q3", "FY"}
                and item.get("filed")
                and item.get("end")
                and item.get("val") is not None
            ]
            latest = max(observations, key=lambda item: (str(item["filed"]), str(item["end"])))
            value = Decimal(str(latest["val"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise MarketInformationError("SEC response lacks a usable reported revenue observation") from exc
        retrieved_at = datetime.now(UTC)
        period = f"{latest.get('fy', '')} {latest.get('fp', '')}".strip()
        fact = MarketInformationFact(
            claim=f"{request.symbol.upper()} SEC reported revenue ({period})",
            value=value,
            source_path="facts.us-gaap.RevenueFromContractWithCustomerExcludingAssessedTax.units.USD",
            source_url=facts_url,
            retrieved_at=retrieved_at,
            provenance={
                "form": str(latest["form"]),
                "filed": str(latest["filed"]),
                "period_end": str(latest["end"]),
                "accession": str(latest.get("accn", "")),
                "fiscal_period": period,
            },
        )
        return MarketInformationResult(
            findings=("A dated SEC-filed operating revenue observation is now available.",),
            facts=(fact,),
            limitations=(
                "This filing observation reports one historical period; it is not management guidance and does not alter Java forecast assumptions.",
            ),
            source="SEC company facts API",
            specialist_latency_ms=(retrieved_at - started).total_seconds() * 1000,
        )
