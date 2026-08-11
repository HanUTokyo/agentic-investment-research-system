from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.contracts import Evidence, ValuationReport, ValuationScenario
from app.research_case import ResearchAction, ResearchCase, ResearchEvidence
from app.research_graph import ResearchDispatcher, build_research_graph


@pytest.mark.asyncio
async def test_graph_routes_controller_selected_evidence_action_without_semantic_edges() -> None:
    class Controller:
        def __init__(self):
            self.actions = iter((
                ResearchAction(action="REQUEST_EVIDENCE", reason="Need filing", request="filing"),
                ResearchAction(action="FINALIZE", reason="Evidence is sufficient"),
            ))

        async def decide(self, _case):
            return next(self.actions)

    async def evidence_executor(_case, _action):
        return (ResearchEvidence(evidence_id="filing", evidence=Evidence(claim="Filing", source_path="external.filing"), source="SEC", source_type="external", provenance={"locator": "10-K"}),)

    report = ValuationReport(
        symbol="ACME", conclusion="Grounded conclusion", valuation_basis="FCFF", engine_version="java-1",
        scenario_results=[ValuationScenario(scenario_type="BASE", valid=True, intrinsic_value_per_share=Decimal("10"))],
        evidence=[Evidence(claim="Java value", source_path="java.scenarios[0].intrinsic_value_per_share", value=Decimal("10"))],
        trace_id="trace", generated_at=datetime.now(UTC),
    )
    graph = build_research_graph(Controller(), ResearchDispatcher(evidence_executor=evidence_executor))
    config = {"configurable": {"thread_id": "case-1"}}
    result = await graph.ainvoke({"case": ResearchCase(query="q", objective="o", final_report=report)}, config=config)
    finished = result["case"]
    assert finished.status == "FINALIZED"
    assert finished.iteration_count == 2
    assert [item.action.action for item in finished.executed_actions] == ["REQUEST_EVIDENCE", "FINALIZE"]
    assert graph.get_state(config).values["case"] == finished
