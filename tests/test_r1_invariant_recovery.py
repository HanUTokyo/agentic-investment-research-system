import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.clients.ai_router import RoutedCompletion
from app.clients.mock_stock_platform import MockStockPlatformClient
from app.experiments.invariant_recovery_probe import (
    R1AssistedInvariantRecoveryAgent,
    RuntimeForcedR1RecoveryAgent,
)


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


@pytest.mark.asyncio
async def test_recovery_reason_keeps_content_empty_unknown_on_transport_failure() -> None:
    class _FailingRouter:
        async def complete(self, _messages, **_kwargs):
            raise ConnectionError("router unavailable")

    agent = R1AssistedInvariantRecoveryAgent(
        MockStockPlatformClient(Path("fixtures/stock_platform")),
        recovery_client=_FailingRouter(),
        llm=MagicMock(),
    )
    agent.last_invariant_feedback = "ERROR_TYPE: INVALID_EVIDENCE_PATH"

    with pytest.raises(RuntimeError, match="ConnectionError"):
        await agent.delegate_recovery_reason()

    assert agent.r1_content_empty is None


@pytest.mark.asyncio
async def test_runtime_forces_one_typed_plan_after_matching_invariant() -> None:
    agent = RuntimeForcedR1RecoveryAgent(
        MockStockPlatformClient(Path("fixtures/stock_platform")),
        recovery_client=_RecoveryRouter(
            json.dumps(
                {
                    "error_type": "INVALID_EVIDENCE_PATH",
                    "diagnosis": "The evidence path is invalid.",
                    "recommended_action": "Request a Java-backed candidate.",
                    "required_tool": "get_probe_valid_report",
                    "expected_evidence": "Java compact observation",
                }
            )
        ),
        llm=MagicMock(),
    )
    agent.last_invariant_feedback = "ERROR_TYPE: INVALID_EVIDENCE_PATH"

    assert agent.should_force_runtime_recovery() is True
    await agent.force_runtime_recovery_plan()

    assert agent.runtime_recovery_triggered is True
    assert agent.recovery_plan is not None
    assert "RUNTIME_RECOVERY_PLAN" in agent.runtime_recovery_observation()
    assert agent.should_force_runtime_recovery() is False


@pytest.mark.asyncio
async def test_runtime_preserves_r1_transport_failure_as_observation() -> None:
    class _FailingRouter:
        async def complete(self, _messages, **_kwargs):
            raise ConnectionError("router unavailable")

    agent = RuntimeForcedR1RecoveryAgent(
        MockStockPlatformClient(Path("fixtures/stock_platform")),
        recovery_client=_FailingRouter(),
        llm=MagicMock(),
    )
    agent.last_invariant_feedback = "ERROR_TYPE: INVALID_EVIDENCE_PATH"

    await agent.force_runtime_recovery_plan()

    assert agent.runtime_recovery_triggered is True
    assert agent.recovery_plan is None
    assert "RUNTIME_RECOVERY_FAILURE" in agent.runtime_recovery_observation()
