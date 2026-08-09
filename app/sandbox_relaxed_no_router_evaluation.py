"""Run the separately labelled relaxed no-router NOOA comparison condition."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from nooa.events import Error, LLMOutput, Task

from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.config import get_settings
from app.evaluation.four_way import FrozenValuationClient
from app.evaluation.relaxed_no_router import RelaxedNoRouterValuationAgent
from app.llm import build_nooa_controller_llm

CASE_PATH = Path("/sandbox/fixtures/eval/phase1b_aapl.json")


class RawTrace:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def attach(self, event_manager: Any) -> None:
        event_manager.on("*", self._on_event)

    def _on_event(self, event: Any) -> None:
        if isinstance(event, Task):
            self.events.append({"type": "prompt", "content": event.prompt})
        elif isinstance(event, LLMOutput):
            self.events.append({"type": "completion", "content": event.content})
        elif isinstance(event, Error):
            self.events.append({"type": "validation_error", "content": event.content})


async def main() -> None:
    data, question = FrozenValuationClient.from_path(CASE_PATH)
    agent = RelaxedNoRouterValuationAgent(
        data, reasoning_client=None, llm=build_nooa_controller_llm(get_settings())
    )
    trace = RawTrace()
    trace.attach(agent.event_manager)
    started = perf_counter()
    try:
        report = await agent.investigate_relaxed_no_router(question=question, symbol="AAPL")
        result: dict[str, object] = {
            "event": "relaxed_no_router_nooa_evaluation",
            "case": "synthetic-aapl-phase1b-v1",
            "success": True,
            "latency_ms": (perf_counter() - started) * 1000,
            "raw_trace": trace.events,
            "trajectory": agent.phase1b_trace.trajectory,
            "grounding_success": all_scenario_values_grounded(report),
            "unsupported_numerical_claim_count": unsupported_numerical_claim_count(report),
            "report": report.model_dump(mode="json"),
        }
    except Exception as exc:
        result = {
            "event": "relaxed_no_router_nooa_evaluation",
            "case": "synthetic-aapl-phase1b-v1",
            "success": False,
            "latency_ms": (perf_counter() - started) * 1000,
            "raw_trace": trace.events,
            "trajectory": agent.phase1b_trace.trajectory,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1_000],
        }
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
