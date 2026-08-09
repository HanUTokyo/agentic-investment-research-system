"""Run one real NOOA ValuationAgent invariant-recovery probe in the sandbox."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from time import perf_counter
from typing import cast
from uuid import uuid4

from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.clients import StockPlatformClient
from app.config import get_settings
from app.experiments.invariant_recovery_probe import (
    InvariantRecoveryValuationAgent,
    ProbeCase,
)
from app.llm import build_nooa_controller_llm


async def main() -> None:
    configured_case = os.environ.get("INVARIANT_RECOVERY_CASE", "missing_initial_evidence")
    if configured_case not in {
        "missing_initial_evidence",
        "unsupported_numeric_claim",
        "invalid_evidence_path",
    }:
        raise ValueError("invalid INVARIANT_RECOVERY_CASE")
    probe_case = cast(ProbeCase, configured_case)
    settings = get_settings()
    stock = StockPlatformClient(settings)
    agent = InvariantRecoveryValuationAgent(
        stock,
        probe_case=probe_case,
        llm=build_nooa_controller_llm(settings),
    )
    run_id = str(uuid4())
    started = perf_counter()
    try:
        report = await asyncio.wait_for(agent.recover_invariant("AAPL"), timeout=600)
        grounding_success = unsupported_numerical_claim_count(
            report
        ) == 0 and all_scenario_values_grounded(report)
        recovered = bool(agent.invariant_feedback) and bool(agent.corrective_actions)
        outcome: dict[str, object] = {
            "native_return_result_success": True,
            "grounding_success": grounding_success,
            "success": grounding_success and recovered,
            "final_failure_reason": (
                None
                if grounding_success and recovered
                else "grounding_gate_failed" if not grounding_success else "no_recovery_observed"
            ),
        }
    except Exception as exc:
        outcome = {
            "native_return_result_success": False,
            "grounding_success": False,
            "success": False,
            "final_failure_reason": type(exc).__name__,
            "error": str(exc)[:500],
        }
    finally:
        await stock.aclose()
    print(
        json.dumps(
            {
                "event": "valuation_invariant_recovery_probe",
                "run_id": run_id,
                "case": probe_case,
                "started_at": datetime.now(UTC).isoformat(),
                "latency_ms": (perf_counter() - started) * 1000,
                "initial_error_type": {
                    "missing_initial_evidence": "MISSING_INITIAL_EVIDENCE",
                    "unsupported_numeric_claim": "UNSUPPORTED_NUMERIC_CLAIM",
                    "invalid_evidence_path": "INVALID_EVIDENCE_PATH",
                }[probe_case],
                "feedback_delivered": bool(agent.invariant_feedback),
                "controller_corrective_action": agent.corrective_actions,
                "recovery_iterations": len(agent.invariant_feedback),
                "java_calls": [item.model_dump() for item in agent.tool_calls],
                "r1_calls": 0,
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
