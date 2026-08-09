"""One real, serial Phase 1B AAPL acceptance run in the restricted sandbox."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.agents import ConstrainedTypedValuationAgent
from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.clients import RouterClient, StockPlatformClient
from app.config import get_settings
from app.llm import build_nooa_controller_llm

QUESTION = (
    "Why is AAPL's current market price above the base intrinsic value, and what is "
    "the most important valuation uncertainty to investigate?"
)


async def main() -> None:
    settings = get_settings()
    run_id = str(uuid4())
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    agent = ConstrainedTypedValuationAgent(
        stock,
        reasoning_client=router,
        llm=build_nooa_controller_llm(settings),
    )
    started = perf_counter()
    try:
        report = await asyncio.wait_for(
            agent.investigate_constrained(question=QUESTION, symbol="AAPL"), timeout=900
        )
        trace = agent.phase1b_trace
        unsupported = unsupported_numerical_claim_count(report)
        grounded = all_scenario_values_grounded(report)
        strict = (
            trace.typed_decisions_total > 0
            and trace.typed_decisions_total == trace.typed_decisions_valid
            and trace.typed_decision_failures == 0
            and trace.dispatcher_failures == 0
            and trace.scenario_calls <= 1
            and trace.r1_calls <= 1
            and trace.typed_final_success
            and grounded
            and unsupported == 0
        )
        outcome: dict[str, object] = {
            "success": strict,
            "typed_final_success": trace.typed_final_success,
            "grounding_success": grounded,
            "unsupported_numerical_claim_count": unsupported,
            "report_summary": {
                "symbol": report.symbol,
                "valuation_basis": report.valuation_basis,
                "scenario_types": [item.scenario_type for item in report.scenario_results],
                "evidence_source_paths": [item.source_path for item in report.evidence],
            },
        }
    except Exception as exc:
        trace = agent.phase1b_trace
        outcome = {
            "success": False,
            "typed_final_success": trace.typed_final_success,
            "grounding_success": trace.grounding_success,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    finally:
        await stock.aclose()
        await router.aclose()

    print(
        json.dumps(
            {
                "event": "phase1b_constrained_valuation_acceptance",
                "run_id": run_id,
                "started_at": datetime.now(UTC).isoformat(),
                "total_latency_ms": (perf_counter() - started) * 1000,
                "trajectory": trace.trajectory,
                "metrics": {
                    "typed_decisions_total": trace.typed_decisions_total,
                    "typed_decisions_valid": trace.typed_decisions_valid,
                    "typed_decision_failures": trace.typed_decision_failures,
                    "dispatcher_actions_total": trace.dispatcher_actions_total,
                    "dispatcher_failures": trace.dispatcher_failures,
                    "r1_calls": trace.r1_calls,
                    "scenario_calls": trace.scenario_calls,
                    "recovery_decisions": trace.recovery_decisions,
                    "finalization_attempts": trace.finalization_attempts,
                    "typed_final_success": trace.typed_final_success,
                    "grounding_success": trace.grounding_success,
                    "failure_classification": trace.failure_classification,
                },
                "coder_calls": 0,
                "gemma_calls": 0,
                **outcome,
            },
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
