from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.constrained_valuation_agent import (
    ConstrainedTypedValuationAgent,
    DispatcherError,
)
from app.agents.valuation_projection import CompactScenarioObservation
from app.clients.mock_stock_platform import MockStockPlatformClient
from app.contracts import NextActionDecision, ValuationSynthesis


@pytest.mark.asyncio
async def test_phase1b_materializes_only_java_backed_numeric_fields() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ConstrainedTypedValuationAgent(client, llm=MagicMock())
    compact = await agent.get_compact_valuation("demo")
    report = agent._materialize_report(
        compact,
        None,
        ValuationSynthesis(
            conclusion="The valuation evidence supports a qualitative comparison.",
            valuation_basis="FCFF",
            primary_uncertainty="The published valuation warning needs review.",
            uncertainty_severity="medium",
        ),
    )

    agent.validate_final_report(report)
    assert report.evidence[0].source_path == "java.compact_valuation.overview.current_price"
    assert all("intrinsic_value_per_share" in item.source_path for item in report.evidence[1:])


@pytest.mark.asyncio
async def test_phase1b_rejects_synthesis_that_changes_java_model() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ConstrainedTypedValuationAgent(client, llm=MagicMock())
    compact = await agent.get_compact_valuation("demo")

    with pytest.raises(ValueError, match="selected_model"):
        agent._materialize_report(
            compact,
            None,
            ValuationSynthesis(
                conclusion="A qualitative conclusion.",
                valuation_basis="FCFE",
                primary_uncertainty="A qualitative uncertainty.",
                uncertainty_severity="medium",
            ),
        )


@pytest.mark.asyncio
async def test_phase1b_dispatcher_bounds_reason_and_scenario_actions() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ConstrainedTypedValuationAgent(client, llm=MagicMock())
    compact = await agent.get_compact_valuation("demo")
    scenario = CompactScenarioObservation(
        scenario_type="BULL",
        selected_model="FCFF",
        valid=True,
        intrinsic_value_per_share=compact.base_value,
        margin_of_safety_price=None,
    )

    with pytest.raises(DispatcherError, match="at most once"):
        await agent._dispatch(
            NextActionDecision(action="RUN_SCENARIO", reason="already used"),
            "demo",
            compact,
            None,
            scenario,
        )
