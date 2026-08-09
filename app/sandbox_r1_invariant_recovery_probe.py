"""Run the real R1-assisted INVALID_EVIDENCE_PATH recovery probe."""

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
from app.experiments.invariant_recovery_probe import R1AssistedInvariantRecoveryAgent
from app.llm import build_nooa_controller_llm


async def main() -> None:
    settings = get_settings()
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    agent = R1AssistedInvariantRecoveryAgent(
        stock,
        recovery_client=router,
        llm=build_nooa_controller_llm(settings),
    )
    run_id = str(uuid4())
    started = perf_counter()
    try:
        report = await asyncio.wait_for(agent.recover_with_r1("AAPL"), timeout=720)
        grounding_success = unsupported_numerical_claim_count(
            report
        ) == 0 and all_scenario_values_grounded(report)
        followed_plan = "requested_valid_java_backed_report_candidate" in agent.corrective_actions
        outcome: dict[str, object] = {
            "native_return_result_success": True,
            "grounding_success": grounding_success,
            "controller_corrective_tool_called": followed_plan,
            "success": grounding_success and followed_plan and agent.recovery_plan is not None,
            "final_failure_reason": None,
        }
    except Exception as exc:
        outcome = {
            "native_return_result_success": False,
            "grounding_success": False,
            "controller_corrective_tool_called": bool(agent.corrective_actions),
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
                "event": "r1_assisted_invariant_recovery_probe",
                "run_id": run_id,
                "started_at": datetime.now(UTC).isoformat(),
                "latency_ms": (perf_counter() - started) * 1000,
                "invariant_error": agent.invariant_feedback[-1]
                if agent.invariant_feedback
                else None,
                "r1_called": agent.r1_content_empty is not None,
                "r1_content_empty": agent.r1_content_empty,
                "r1_latency_ms": agent.r1_latency_ms,
                "r1_error_type": agent.r1_error_type,
                "recovery_plan_valid": agent.recovery_plan is not None,
                "recommended_tool": (
                    agent.recovery_plan.required_tool if agent.recovery_plan else None
                ),
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
