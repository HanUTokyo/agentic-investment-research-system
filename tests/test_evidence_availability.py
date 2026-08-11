import pytest

from app.contracts import Evidence, FinancialHistory
from app.evidence_availability_executor import FiscalRevenueAvailabilityExecutor
from app.research_case import (
    EvidenceRequestTarget,
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
    ResearchUncertainty,
)
from app.research_graph import ResearchDispatcher


def _history() -> FinancialHistory:
    rows = []
    for period, date in (("Q1", "2025-12-27"), ("Q2", "2026-03-28"), ("Q3", "2026-06-27")):
        rows.append(
            {
                "asOfDate": date,
                "fiscalYear": 2026,
                "fiscalPeriod": period,
                "forecast": False,
                "revenue": 100,
                "fieldMetadata": {
                    "revenue": {"sourceCode": "SEC_COMPANY_FACTS", "sourceDate": "2026-07-31"}
                },
            }
        )
    return FinancialHistory(symbol="AAPL", quarterly_fundamentals=rows)


def _action() -> ResearchAction:
    return ResearchAction(
        action="REQUEST_EVIDENCE",
        reason="Need the next reported revenue period.",
        request="Retrieve AAPL FY2026 Q4 SEC-reported revenue.",
        evidence_target=EvidenceRequestTarget(
            evidence_type="SEC_REPORTED_REVENUE",
            symbol="AAPL",
            fiscal_year=2026,
            fiscal_period="Q4",
        ),
    )


@pytest.mark.asyncio
async def test_not_yet_available_request_persists_deterministic_outcome() -> None:
    availability = FiscalRevenueAvailabilityExecutor.availability_from_history("AAPL", _history())
    case = ResearchCase(
        query="q",
        objective="o",
        valuation_context={"symbol": "AAPL"},
        evidence_availability=(availability,),
    )
    executor = FiscalRevenueAvailabilityExecutor()
    updated = await ResearchDispatcher(evidence_executor=executor).dispatch(case.select(_action()))

    assert executor.invocation_count == 1
    assert updated.evidence == ()
    outcome = updated.evidence_request_outcomes[-1]
    assert outcome.status == "NOT_YET_AVAILABLE"
    assert outcome.target.fiscal_period == "Q4"
    assert "latest available period is 2026 Q3" in outcome.reason


@pytest.mark.asyncio
async def test_availability_executor_rejects_available_or_untyped_requests() -> None:
    availability = FiscalRevenueAvailabilityExecutor.availability_from_history("AAPL", _history())
    executor = FiscalRevenueAvailabilityExecutor()
    case = ResearchCase(query="q", objective="o", evidence_availability=(availability,))
    available = _action().model_copy(
        update={
            "evidence_target": EvidenceRequestTarget(
                evidence_type="SEC_REPORTED_REVENUE",
                symbol="AAPL",
                fiscal_year=2026,
                fiscal_period="Q3",
            )
        }
    )
    with pytest.raises(IllegalResearchTransition, match="not NOT_YET_AVAILABLE"):
        await executor(case, available)
    with pytest.raises(IllegalResearchTransition, match="typed evidence target"):
        await executor(case, ResearchAction(action="REQUEST_EVIDENCE", reason="x", request="x"))


@pytest.mark.asyncio
async def test_controller_selected_limited_closure_requires_only_known_uncertainties() -> None:
    forecast = ResearchEvidence(
        evidence_id="forecast",
        evidence=Evidence(claim="forecast caveat", source_path="java.forecast"),
        source="Java",
        source_type="deterministic_valuation",
        numerical_authority="deterministic_valuation",
    )
    case = ResearchCase(
        query="q",
        objective="o",
        evidence=(forecast,),
        tracked_uncertainties=(
            ResearchUncertainty(
                uncertainty_id="nwc",
                description="NWC remains limited.",
                source_evidence_id="forecast",
            ),
        ),
    )
    closing = ResearchAction(
        action="FINALIZE",
        reason="Close with the disclosed NWC limitation.",
        unresolved_uncertainty_ids=("nwc",),
    )
    closed = await ResearchDispatcher().dispatch(case.select(closing))
    assert closed.status == "FINALIZED_WITH_LIMITATIONS"
    invalid = ResearchAction(action="FINALIZE", reason="x", unresolved_uncertainty_ids=("unknown",))
    with pytest.raises(IllegalResearchTransition, match="tracked uncertainties"):
        await ResearchDispatcher().dispatch(case.select(invalid))
