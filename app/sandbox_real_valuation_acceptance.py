"""One bounded, real AAPL ValuationAgent acceptance run in the Docker sandbox."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.agents import ValuationAgent
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
    agent = ValuationAgent(
        stock,
        reasoning_client=router,
        llm=build_nooa_controller_llm(settings),
    )
    started = perf_counter()
    try:
        report = await asyncio.wait_for(
            agent.investigate(question=QUESTION, symbol="AAPL"), timeout=900
        )
        unsupported = unsupported_numerical_claim_count(report)
        strict = (
            any(
                item.tool_name == "get_current_valuation" and item.success
                for item in agent.tool_calls
            )
            and len(agent.reason_results) <= 1
            and agent.scenario_call_count <= 1
            and "draft_python" not in [item.tool_name for item in agent.tool_calls]
            and unsupported == 0
            and all_scenario_values_grounded(report)
        )
        outcome: dict[str, object] = {
            "success": strict,
            "final_return_valid": True,
            "unsupported_numerical_claim_count": unsupported,
            "scenario_values_grounded": all_scenario_values_grounded(report),
            "report_summary": {
                "symbol": report.symbol,
                "valuation_basis": report.valuation_basis,
                "engine_version": report.engine_version,
                "scenario_types": [item.scenario_type for item in report.scenario_results],
                "evidence_source_paths": [item.source_path for item in report.evidence],
            },
            "acceptance_error": None if strict else "strict_real_valuation_acceptance_failed",
        }
    except Exception as exc:
        outcome = {
            "success": False,
            "final_return_valid": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    finally:
        await stock.aclose()
        await router.aclose()

    reason = agent.reason_results[0].worker if agent.reason_results else None
    print(
        json.dumps(
            {
                "event": "real_valuation_agent_acceptance",
                "run_id": run_id,
                "started_at": datetime.now(UTC).isoformat(),
                "latency_ms": (perf_counter() - started) * 1000,
                "tool_calls": [item.model_dump() for item in agent.tool_calls],
                "r1_invoked": reason is not None,
                "r1_http_success": reason.http_success if reason else None,
                "r1_content_empty": reason.content_empty if reason else None,
                "r1_success": reason.ok if reason else None,
                "r1_latency_ms": reason.latency_ms if reason else None,
                "r1_model": reason.model if reason else None,
                "scenario_invoked": agent.scenario_call_count > 0,
                "scenario_call_count": agent.scenario_call_count,
                "controller_recovery_count": None,
                "coder_calls": 0,
                "gemma_calls": 0,
                **outcome,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
