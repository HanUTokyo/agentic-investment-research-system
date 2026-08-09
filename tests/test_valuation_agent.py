from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents import ValuationAgent
from app.clients.mock_stock_platform import MockStockPlatformClient
from app.contracts import CodeDraft, CodeTask


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
