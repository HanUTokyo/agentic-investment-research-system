import json

import pytest

from app.contracts import Evidence, FinancialHistory
from app.net_working_capital_evidence_executor import NetWorkingCapitalEvidenceExecutor
from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
)
from app.research_graph import ResearchDispatcher, build_research_graph


def _forecast() -> ResearchEvidence:
    return ResearchEvidence(
        evidence_id="forecast",
        evidence=Evidence(
            claim="Java forecast",
            source_path="java.forecast",
            value=json.dumps(
                {
                    "missing_inputs": [
                        "changeInNetWorkingCapital is an explicit analyst assumption until the detailed indirect-CFO bridge is complete."
                    ]
                }
            ),
        ),
        source="Java",
        source_type="deterministic_valuation",
        numerical_authority="deterministic_valuation",
        claim_scope=("explicit_forecast",),
    )


def _row(index: int) -> dict[str, object]:
    return {
        "asOfDate": f"2026-0{index}-28",
        "fiscalYear": 2026,
        "fiscalPeriod": f"Q{index}",
        "filingDate": f"2026-0{index + 1}-01",
        "forecast": False,
        "changeInWorkingCapital": str(index * 10),
        "revenue": "1000",
        "fieldMetadata": {
            "changeInWorkingCapital": {
                "sourceCode": "SEC_COMPANY_FACTS",
                "sourceDate": "2026-01-01",
            },
            "revenue": {"sourceCode": "SEC_COMPANY_FACTS", "sourceDate": "2026-01-01"},
        },
    }


class _Stock:
    async def get_financial_history(self, symbol: str) -> FinancialHistory:
        assert symbol == "AAPL"
        return FinancialHistory(
            symbol=symbol, quarterly_fundamentals=[_row(1), _row(2), _row(3), _row(4)]
        )


def _case() -> ResearchCase:
    return ResearchCase(
        query="q", objective="o", valuation_context={"symbol": "AAPL"}, evidence=(_forecast(),)
    )


def _action(
    request: str = "Retrieve detailed net working capital evidence from Java historical fundamentals.",
) -> ResearchAction:
    return ResearchAction(
        action="REQUEST_EVIDENCE", reason="Forecast caveat needs NWC evidence.", request=request
    )


@pytest.mark.asyncio
async def test_java_nwc_evidence_is_provenance_complete_and_deterministically_derived() -> None:
    executor = NetWorkingCapitalEvidenceExecutor(_Stock())
    evidence = await executor(_case(), _action())

    assert executor.invocation_count == 1
    assert evidence[0].numerical_authority == "deterministic_valuation"
    assert evidence[0].claim_scope == ("net_working_capital", "historical_fundamentals")
    payload = json.loads(str(evidence[0].evidence.value))
    assert payload["period_count"] == 4
    assert payload["periods"][0]["reported_change_in_working_capital_rate"] == "0.01"
    assert (
        payload["periods"][-1]["change_in_working_capital_source"]["sourceCode"]
        == "SEC_COMPANY_FACTS"
    )


@pytest.mark.asyncio
async def test_nwc_requires_controller_selected_request_and_forecast_caveat() -> None:
    executor = NetWorkingCapitalEvidenceExecutor(_Stock())
    with pytest.raises(IllegalResearchTransition, match="bounded NWC"):
        await executor(_case(), _action("get market data"))
    without_caveat = ResearchCase(query="q", objective="o", valuation_context={"symbol": "AAPL"})
    with pytest.raises(IllegalResearchTransition, match="forecast NWC caveat"):
        await executor(without_caveat, _action())


@pytest.mark.asyncio
async def test_nwc_rejects_duplicate_and_incomplete_java_history() -> None:
    executor = NetWorkingCapitalEvidenceExecutor(_Stock())
    existing = ResearchEvidence(
        evidence=Evidence(claim="prior", source_path="java.nwc"),
        source="Java",
        source_type="deterministic_valuation",
        numerical_authority="deterministic_valuation",
        claim_scope=("net_working_capital",),
    )
    with pytest.raises(IllegalResearchTransition, match="already satisfied"):
        await executor(_case().model_copy(update={"evidence": (_forecast(), existing)}), _action())

    class IncompleteStock:
        async def get_financial_history(self, symbol: str) -> FinancialHistory:
            return FinancialHistory(
                symbol=symbol, quarterly_fundamentals=[_row(1), _row(2), _row(3)]
            )

    with pytest.raises(IllegalResearchTransition, match="four provenance"):
        await NetWorkingCapitalEvidenceExecutor(IncompleteStock())(_case(), _action())


@pytest.mark.asyncio
async def test_controller_reassessment_receives_nwc_evidence_through_neutral_graph() -> None:
    class Controller:
        def __init__(self) -> None:
            self.visible: list[tuple[str, ...]] = []

        async def decide(self, case: ResearchCase) -> ResearchAction:
            self.visible.append(tuple(item.evidence_id for item in case.evidence))
            if len(self.visible) == 1:
                return _action()
            return ResearchAction(
                action="DELEGATE_SPECIALIST", reason="Fresh semantic reassessment."
            )

    controller = Controller()
    graph = build_research_graph(
        controller,
        ResearchDispatcher(evidence_executor=NetWorkingCapitalEvidenceExecutor(_Stock())),
    )
    with pytest.raises(IllegalResearchTransition, match="no specialist"):
        await graph.ainvoke(
            {"case": _case()}, config={"configurable": {"thread_id": "nwc-reassessment"}}
        )
    assert controller.visible[0] == ("forecast",)
    assert len(controller.visible[1]) == 2
