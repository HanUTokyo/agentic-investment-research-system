"""Run exactly one A-D ValuationAgent observation replay inside the sandbox."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from time import perf_counter
from typing import cast
from uuid import uuid4

from app.agents.valuation_projection import project_compact_valuation
from app.clients import StockPlatformClient
from app.config import get_settings
from app.experiments.valuation_observation_replay import (
    ValuationObservationReplayAgent,
    Variant,
    make_source,
    observation_metrics,
)
from app.llm import build_nooa_controller_llm


async def main() -> None:
    configured_variant = os.environ.get("OBSERVATION_REPLAY_VARIANT", "A").upper()
    if configured_variant not in {"A", "B", "C", "D"}:
        raise ValueError("OBSERVATION_REPLAY_VARIANT must be A, B, C, or D")
    variant = cast(Variant, configured_variant)
    settings = get_settings()
    stock = StockPlatformClient(settings)
    run_id = str(uuid4())
    try:
        # This one read fixes B's public AAPL facts for all replay variants.
        fixed_raw = await stock.get_current_valuation("AAPL")
        source = make_source(
            variant,
            fixed_compact=project_compact_valuation(fixed_raw),
            stock_fetch=lambda: stock.get_current_valuation("AAPL"),
        )
        preview = await source.preview()
        agent = ValuationObservationReplayAgent(source, llm=build_nooa_controller_llm(settings))
        started = perf_counter()
        try:
            result = await asyncio.wait_for(agent.acknowledge(), timeout=420)
            success = source.calls == 1 and result.controller_observed is True
            outcome: dict[str, object] = {
                "success": success,
                "controller_continuation_success": success,
                "native_return_success": True,
                "result": result.model_dump(),
            }
        except Exception as exc:
            outcome = {
                "success": False,
                "controller_continuation_success": False,
                "native_return_success": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            }
        print(
            json.dumps(
                {
                    "event": "valuation_observation_replay",
                    "run_id": run_id,
                    "variant": variant,
                    "started_at": datetime.now(UTC).isoformat(),
                    "latency_ms": (perf_counter() - started) * 1000,
                    **observation_metrics(preview),
                    "observation_tool_calls": source.calls,
                    "observation_tool_latency_ms": source.latency_ms,
                    "r1_calls": 0,
                    "coder_calls": 0,
                    "gemma_calls": 0,
                    "scenario_calls": 0,
                    **outcome,
                },
                ensure_ascii=False,
            )
        )
    finally:
        await stock.aclose()


if __name__ == "__main__":
    asyncio.run(main())
