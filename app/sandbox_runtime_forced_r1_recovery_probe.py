"""Run the real runtime-forced R1 INVALID_EVIDENCE_PATH recovery probe."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.clients import RouterClient, StockPlatformClient
from app.config import get_settings
from app.experiments.invariant_recovery_probe import RuntimeForcedR1RecoveryAgent
from app.llm import build_nooa_controller_llm


async def main() -> None:
    settings = get_settings()
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    agent = RuntimeForcedR1RecoveryAgent(
        stock,
        recovery_client=router,
        llm=build_nooa_controller_llm(settings),
    )
    run_id = str(uuid4())
    started = perf_counter()
    try:
        report = await asyncio.wait_for(agent.recover_with_runtime_forced_r1("AAPL"), timeout=720)
        grounding_success = unsupported_numerical_claim_count(
            report
        ) == 0 and all_scenario_values_grounded(report)
        corrective_tool_called = (
            "requested_valid_java_backed_report_candidate" in agent.corrective_actions
        )
        outcome: dict[str, object] = {
            "controller_corrective_tool_called": corrective_tool_called,
            "native_return_result_success": True,
            "grounding_success": grounding_success,
            "success": (
                agent.runtime_recovery_triggered
                and agent.recovery_plan is not None
                and corrective_tool_called
                and grounding_success
            ),
            "final_failure_reason": None,
        }
    except Exception as exc:
        outcome = {
            "controller_corrective_tool_called": bool(agent.corrective_actions),
            "native_return_result_success": False,
            "grounding_success": False,
            "success": False,
            "final_failure_reason": type(exc).__name__,
            "error": str(exc)[:500],
        }
    finally:
        await stock.aclose()
        await router.aclose()
    print(
        json.dumps(
            {
                "event": "runtime_forced_r1_recovery_probe",
                "run_id": run_id,
                "started_at": datetime.now(UTC).isoformat(),
                "latency_ms": (perf_counter() - started) * 1000,
                "invariant_error": agent.invariant_feedback[-1]
                if agent.invariant_feedback
                else None,
                "runtime_recovery_triggered": agent.runtime_recovery_triggered,
                "r1_called": agent.r1_invoked,
                "r1_content_empty": agent.r1_content_empty,
                "r1_error_type": agent.r1_error_type,
                "r1_plan_status": agent.r1_plan_status,
                "recovery_plan_valid": agent.recovery_plan is not None,
                "recovery_plan": agent.recovery_plan.model_dump(mode="json")
                if agent.recovery_plan
                else None,
                "controller_received_plan": agent.controller_received_plan,
                "controller_corrective_action": agent.corrective_actions,
                "recovery_iterations": len(agent.invariant_feedback),
                "java_calls": [item.model_dump() for item in agent.tool_calls],
                "coder_calls": 0,
                "gemma_calls": 0,
                "scenario_calls": agent.scenario_call_count,
                **outcome,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
