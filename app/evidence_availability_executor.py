"""Deterministic fiscal-evidence availability checks for bounded Controller requests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from app.contracts import FinancialHistory
from app.research_case import (
    EvidenceAvailability,
    EvidenceRequestOutcome,
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
)
from app.research_graph import EvidenceExecutionResult

_PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}


class FiscalRevenueAvailabilityExecutor:
    """Records NOT_YET_AVAILABLE; it neither retrieves substitute evidence nor plans recovery."""

    def __init__(self) -> None:
        self.invocation_count = 0

    @staticmethod
    def availability_from_history(symbol: str, history: FinancialHistory) -> EvidenceAvailability:
        actual = [
            row
            for row in history.quarterly_fundamentals
            if row.get("forecast") is not True
            and row.get("revenue") is not None
            and isinstance(row.get("fiscalYear"), int)
            and row.get("fiscalPeriod") in _PERIOD_ORDER
            and row.get("asOfDate")
        ]
        if not actual:
            raise IllegalResearchTransition("Java historical fundamentals lack fiscal revenue availability")
        latest = max(
            actual,
            key=lambda row: (int(row["fiscalYear"]), _PERIOD_ORDER[str(row["fiscalPeriod"])]),
        )
        metadata = latest.get("fieldMetadata")
        revenue_source = metadata.get("revenue") if isinstance(metadata, dict) else None
        if not isinstance(revenue_source, dict) or not revenue_source.get("sourceCode"):
            raise IllegalResearchTransition("Java revenue availability lacks field provenance")
        return EvidenceAvailability(
            symbol=symbol.upper(),
            evidence_type="SEC_REPORTED_REVENUE",
            as_of_date=datetime.now(UTC),
            latest_fiscal_year=int(latest["fiscalYear"]),
            latest_fiscal_period=cast(
                Literal["Q1", "Q2", "Q3", "Q4", "FY"], str(latest["fiscalPeriod"])
            ),
            latest_period_end=str(latest["asOfDate"]),
            source="Java Stock Platform historical fundamentals",
            provenance={
                "endpoint": "/api/portfolio/history/fundamentals",
                "revenue_source_code": str(revenue_source["sourceCode"]),
                "revenue_source_date": str(revenue_source.get("sourceDate", "")),
            },
        )

    async def __call__(self, case: ResearchCase, action: ResearchAction) -> EvidenceExecutionResult:
        target = action.evidence_target
        if action.action != "REQUEST_EVIDENCE" or target is None:
            raise IllegalResearchTransition("availability executor requires a typed evidence target")
        if target.evidence_type != "SEC_REPORTED_REVENUE":
            raise IllegalResearchTransition("unsupported evidence availability target")
        availability = next(
            (
                item
                for item in case.evidence_availability
                if item.symbol.upper() == target.symbol.upper()
                and item.evidence_type == target.evidence_type
            ),
            None,
        )
        if availability is None:
            raise IllegalResearchTransition("ResearchCase lacks deterministic evidence availability")
        if not self._after_latest(target.fiscal_year, target.fiscal_period, availability):
            raise IllegalResearchTransition("requested evidence is not NOT_YET_AVAILABLE")
        self.invocation_count += 1
        return EvidenceExecutionResult(
            evidence_request_outcome=EvidenceRequestOutcome(
                action_id=action.action_id,
                target=target,
                status="NOT_YET_AVAILABLE",
                availability_id=availability.availability_id,
                reason=(
                    f"{target.symbol.upper()} {target.fiscal_year} {target.fiscal_period} SEC-reported "
                    f"revenue is not yet available as of {availability.as_of_date.date()}; latest "
                    f"available period is {availability.latest_fiscal_year} {availability.latest_fiscal_period} "
                    f"ending {availability.latest_period_end}."
                ),
            )
        )

    @staticmethod
    def _after_latest(year: int, period: str, availability: EvidenceAvailability) -> bool:
        return (year, _PERIOD_ORDER[period]) > (
            availability.latest_fiscal_year,
            _PERIOD_ORDER[availability.latest_fiscal_period],
        )
