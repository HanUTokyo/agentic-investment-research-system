from pathlib import Path
from unittest.mock import MagicMock

import pytest
from nooa.strategy_validation import InvariantError

from app.agents import ValuationAgent
from app.agents.valuation_projection import project_compact_valuation
from app.clients.ai_router import RoutedCompletion
from app.clients.mock_stock_platform import MockStockPlatformClient
from app.contracts import CodeDraft, CodeTask, ReasonTask, ValuationReport, ValuationSnapshot


@pytest.mark.asyncio
async def test_valuation_agent_exposes_only_read_only_scenario_types() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock())
    evaluation = await agent.run_valuation_scenario("demo", "bear")
    assert evaluation.scenario.scenario_type == "BEAR"
    assert agent.tool_calls[-1].tool_name == "run_valuation_scenario"


@pytest.mark.asyncio
async def test_valuation_agent_rejects_unknown_scenario_type() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock())
    with pytest.raises(ValueError, match="BEAR"):
        await agent.run_valuation_scenario("demo", "CUSTOM")


@pytest.mark.asyncio
async def test_valuation_agent_exposes_worker_as_draft_only_capability() -> None:
    class Worker:
        async def draft(self, task, *, research_id, iteration=None):
            return CodeDraft(code="result = []")

    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock(), code_worker=Worker())
    draft = await agent.draft_python(
        CodeTask(objective="sort", constraints=[], expected_result="list")
    )

    assert draft.code == "result = []"
    assert agent.tool_calls[-1].tool_name == "draft_python"


@pytest.mark.asyncio
async def test_reason_worker_is_bounded_and_marked_untrusted() -> None:
    class ReasoningClient:
        async def complete(self, _messages, **kwargs):
            assert kwargs["route_hint"] == "reason"
            return RoutedCompletion(
                content="Validate the terminal-growth assumption.",
                route="reason",
                model="r1",
                latency_ms=1.0,
                raw={},
            )

    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock(), reasoning_client=ReasoningClient())

    first = await agent.delegate_reason(ReasonTask(prompt="identify one gap"))
    second = await agent.delegate_reason(ReasonTask(prompt="another gap"))

    assert first.worker.ok is True
    assert first.trusted_for_numerical_claims is False
    assert second.worker.error_type == "reason_worker_attempt_limit_exceeded"


@pytest.mark.asyncio
async def test_current_valuation_tool_omits_unneeded_projection_rows() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock())

    valuation = await agent.get_current_valuation("demo")

    assert isinstance(valuation, ValuationSnapshot)
    assert valuation.scenarios
    assert "projection" not in valuation.scenarios[0].model_dump()


@pytest.mark.asyncio
async def test_compact_projection_uses_only_authoritative_snapshot_fields() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    raw = await client.get_current_valuation("demo")

    compact = project_compact_valuation(raw)

    assert compact.symbol == raw.symbol
    assert compact.base_value == raw.overview["baseValue"]
    assert compact.selected_model == raw.selected_model


@pytest.mark.asyncio
async def test_compact_agent_tools_hide_full_java_dto() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock())

    compact = await agent.get_compact_valuation("demo")
    scenario = await agent.run_compact_valuation_scenario("demo", "BEAR")

    assert compact.scenarios
    assert "projection" not in compact.model_dump()
    assert scenario.scenario_type == "BEAR"
    assert [item.tool_name for item in agent.tool_calls] == [
        "get_compact_valuation",
        "run_valuation_scenario",
    ]


@pytest.mark.asyncio
async def test_finalization_requires_initial_compact_valuation_evidence() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock())

    with pytest.raises(InvariantError, match="get_compact_valuation"):
        agent.validate_can_finalize()

    await agent.get_compact_valuation("demo")
    agent.validate_can_finalize()


@pytest.mark.asyncio
async def test_finalization_rejects_unsupported_numerical_prose() -> None:
    client = MockStockPlatformClient(Path("fixtures/stock_platform"))
    agent = ValuationAgent(client, llm=MagicMock())
    await agent.get_compact_valuation("demo")
    report = ValuationReport(
        symbol="DEMO",
        conclusion="The value is 42.",
        valuation_basis="FCFE",
        engine_version="v1",
        scenario_results=[],
        evidence=[],
        trace_id="test",
        generated_at=agent.report_timestamp(),
    )

    with pytest.raises(InvariantError, match="unsupported numerical"):
        agent.validate_final_report(report)
