import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.clients.ai_router import RoutedCompletion
from app.clients.mock_stock_platform import MockStockPlatformClient
from app.experiments.invariant_recovery_probe import R1AssistedInvariantRecoveryAgent


class _RecoveryRouter:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        assert kwargs["route_hint"] == "reason"
        assert kwargs["temperature"] == 0
        assert "INVALID_EVIDENCE_PATH" in messages[1]["content"]
        return RoutedCompletion(
            content=self.content,
            route="reason",
            model="deepseek-r1:8b",
            latency_ms=1.0,
            raw={},
        )


@pytest.mark.asyncio
async def test_recovery_reason_returns_strict_typed_plan_once() -> None:
    router = _RecoveryRouter(
        json.dumps(
            {
                "error_type": "INVALID_EVIDENCE_PATH",
                "diagnosis": "The bear evidence path is not Java-backed.",
                "recommended_action": "Request the valid Java-backed candidate.",
                "required_tool": "get_probe_valid_report",
                "expected_evidence": "Java compact observation intrinsic value path",
            }
        )
    )
    agent = R1AssistedInvariantRecoveryAgent(
        MockStockPlatformClient(Path("fixtures/stock_platform")),
        recovery_client=router,
        llm=MagicMock(),
    )
    agent.last_invariant_feedback = (
        "ERROR_TYPE: INVALID_EVIDENCE_PATH\nFIELD: scenario intrinsic_value_per_share evidence"
    )

    plan = await agent.delegate_recovery_reason()

    assert plan.required_tool == "get_probe_valid_report"
    assert agent.r1_content_empty is False
    assert router.calls == 1
    with pytest.raises(RuntimeError, match="only once"):
        await agent.delegate_recovery_reason()


@pytest.mark.asyncio
async def test_recovery_reason_rejects_non_json_without_repair() -> None:
    agent = R1AssistedInvariantRecoveryAgent(
        MockStockPlatformClient(Path("fixtures/stock_platform")),
        recovery_client=_RecoveryRouter("```json\n{}\n```"),
        llm=MagicMock(),
    )
    agent.last_invariant_feedback = "ERROR_TYPE: INVALID_EVIDENCE_PATH"

    with pytest.raises(RuntimeError, match="JSONDecodeError"):
        await agent.delegate_recovery_reason()

    assert agent.recovery_plan is None
    assert agent.r1_content_empty is False
