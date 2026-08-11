"""Deterministic Java-fundamentals evidence for a Controller-selected NWC inquiry."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.contracts import Evidence, FinancialHistory
from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
)

_NWC_MARKERS = ("net working capital", "working capital", "nwc", "indirect cfo")
_REQUIRED_FORECAST_CAVEAT = "changeinnetworkingcapital"
_MAX_PERIODS = 4


class NetWorkingCapitalEvidenceExecutor:
    """Retrieves Java's historical NWC observations; it never selects the inquiry."""

    def __init__(self, stock_platform: Any) -> None:
        self._stock_platform = stock_platform
        self.invocation_count = 0

    async def __call__(
        self, case: ResearchCase, action: ResearchAction
    ) -> tuple[ResearchEvidence, ...]:
        self._validate_request(case, action)
        symbol = str(case.valuation_context.get("symbol", "")).strip().upper()
        history: FinancialHistory = await self._stock_platform.get_financial_history(symbol)
        rows = self._recent_observations(history.quarterly_fundamentals)
        self.invocation_count += 1
        retrieved_at = datetime.now(UTC)
        summary = {
            "capability": "HISTORICAL_NWC_OBSERVATIONS",
            "symbol": symbol,
            "period_count": len(rows),
            "derivation_rule": "REPORTED_CHANGE_IN_WORKING_CAPITAL_RATE_V1: changeInWorkingCapital / revenue",
            "periods": rows,
            "limitations": [
                "The reported cash-flow working-capital field is retained with its Java/SEC provenance.",
                "Its sign and aggregation are not treated as an automatic replacement for the explicit-forecast changeInNetWorkingCapital assumption.",
                "Detailed indirect-CFO bridge completeness remains a separate uncertainty unless the Controller finds this evidence sufficient.",
            ],
        }
        return (
            ResearchEvidence(
                evidence=Evidence(
                    claim=f"Java historical net working-capital observations for {symbol}",
                    source_path="java.portfolio.history.fundamentals.changeInWorkingCapital",
                    value=json.dumps(summary, sort_keys=True, separators=(",", ":")),
                ),
                source="Java Stock Platform historical fundamentals",
                source_type="deterministic_valuation",
                retrieved_at=retrieved_at,
                claim_scope=("net_working_capital", "historical_fundamentals"),
                provenance={
                    "endpoint": "/api/portfolio/history/fundamentals",
                    "symbol": symbol,
                    "derivation_rule": "REPORTED_CHANGE_IN_WORKING_CAPITAL_RATE_V1: changeInWorkingCapital / revenue",
                    "source_fields": "changeInWorkingCapital,revenue,fiscalYear,fiscalPeriod,filingDate,fieldMetadata",
                    "originating_action_id": action.action_id,
                },
                numerical_authority="deterministic_valuation",
            ),
        )

    @staticmethod
    def _validate_request(case: ResearchCase, action: ResearchAction) -> None:
        request = (action.request or "").lower()
        if action.action != "REQUEST_EVIDENCE" or not any(marker in request for marker in _NWC_MARKERS):
            raise IllegalResearchTransition("NWC executor accepts a bounded NWC REQUEST_EVIDENCE only")
        if any("net_working_capital" in item.claim_scope for item in case.evidence):
            raise IllegalResearchTransition("NWC evidence request is already satisfied")
        forecast_payloads = [
            item.evidence.value
            for item in case.evidence
            if "explicit_forecast" in item.claim_scope
            and item.source_type == "deterministic_valuation"
        ]
        if not any(NetWorkingCapitalEvidenceExecutor._has_nwc_caveat(value) for value in forecast_payloads):
            raise IllegalResearchTransition("NWC evidence requires a deterministic forecast NWC caveat")

    @staticmethod
    def _has_nwc_caveat(value: Any) -> bool:
        try:
            payload = json.loads(str(value))
            missing = payload.get("missing_inputs", [])
            return isinstance(missing, list) and any(
                _REQUIRED_FORECAST_CAVEAT in str(item).lower() for item in missing
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _recent_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        for row in rows:
            if row.get("forecast") is True:
                continue
            value = row.get("changeInWorkingCapital")
            revenue = row.get("revenue")
            if value is None or revenue is None:
                continue
            try:
                change = Decimal(str(value))
                sales = Decimal(str(revenue))
            except (InvalidOperation, ValueError) as exc:
                raise IllegalResearchTransition("Java NWC history contains non-numerical values") from exc
            if sales == 0:
                raise IllegalResearchTransition("Java NWC history contains zero revenue")
            metadata = row.get("fieldMetadata")
            source = metadata.get("changeInWorkingCapital") if isinstance(metadata, dict) else None
            if not isinstance(source, dict) or not source.get("sourceCode"):
                raise IllegalResearchTransition("Java NWC history lacks field-level provenance")
            observations.append(
                {
                    "as_of_date": row.get("asOfDate"),
                    "fiscal_year": row.get("fiscalYear"),
                    "fiscal_period": row.get("fiscalPeriod"),
                    "filing_date": row.get("filingDate"),
                    "reported_change_in_working_capital": str(change),
                    "revenue": str(sales),
                    "reported_change_in_working_capital_rate": str(change / sales),
                    "change_in_working_capital_source": source,
                    "revenue_source": metadata.get("revenue") if isinstance(metadata, dict) else None,
                }
            )
        observations.sort(key=lambda item: str(item["as_of_date"]))
        if len(observations) < _MAX_PERIODS:
            raise IllegalResearchTransition("Java NWC history requires four provenance-complete actual periods")
        return observations[-_MAX_PERIODS:]
