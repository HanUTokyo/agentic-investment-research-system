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
    """Retrieve the external 52-week trading range from Yahoo Finance chart data.

    The narrow source is intentional: this validates specialist delegation and
    provenance persistence, not general web research or causal interpretation.
    """

    _URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def collect(self, request: MarketInformationRequest) -> MarketInformationResult:
        started = datetime.now(UTC)
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
