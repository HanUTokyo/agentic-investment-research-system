"""Opt-in trajectory diagnosis for the bounded real AAPL Phase 1 acceptance."""

from __future__ import annotations

import asyncio
import json
from time import perf_counter

from app.agents import ValuationAgent
from app.clients import RouterClient, StockPlatformClient
from app.config import get_settings
from app.experiments.valuation_trajectory import ValuationTrajectoryRecorder
from app.llm import build_nooa_controller_llm
from app.sandbox_real_valuation_acceptance import QUESTION


async def main() -> None:
    settings = get_settings()
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    agent = ValuationAgent(stock, reasoning_client=router, llm=build_nooa_controller_llm(settings))
    recorder = ValuationTrajectoryRecorder()
    recorder.attach(agent.event_manager)
    started = perf_counter()
    try:
        await asyncio.wait_for(agent.investigate(question=QUESTION, symbol="AAPL"), timeout=900)
        outcome: dict[str, object] = {"completed": True, "error_type": None, "error": None}
    except Exception as exc:
        outcome = {
            "completed": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1000],
        }
    finally:
        await stock.aclose()
        await router.aclose()
    print(
        json.dumps(
            {
                "event": "phase1_trajectory_probe",
                "latency_ms": (perf_counter() - started) * 1000,
                "trajectory": recorder.finalize(agent.event_manager),
                "tool_calls": [item.model_dump() for item in agent.tool_calls],
                **outcome,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
