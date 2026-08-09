"""Opt-in serial Router capability probe over public/synthetic AAPL observations.

This does not alter a valuation report. Coder produces an unexecuted draft for a
non-financial list transformation; Gemma produces an untrusted warning summary.
"""

from __future__ import annotations

import asyncio
import json
from time import perf_counter
from uuid import uuid4

from app.agents.valuation_projection import project_compact_valuation
from app.clients import RouterClient, StockPlatformClient
from app.config import get_settings
from app.contracts import CodeTask
from app.workers import RouterCodeWorker


async def main() -> None:
    settings = get_settings()
    run_id = str(uuid4())
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    worker = RouterCodeWorker(router)
    started = perf_counter()
    try:
        raw = await stock.get_current_valuation("AAPL")
        compact = project_compact_valuation(raw)
        task = CodeTask(
            objective="Return a minimal Python draft that creates sorted unique scenario types.",
            known_variables={"scenario_types": "list[str]"},
            constraints=[
                "Use only scenario_types.",
                "Do not import modules.",
                "Do not calculate valuation metrics, DCF, prices, or returns.",
                "Do not execute tools, files, shell, or network operations.",
            ],
            expected_result="A variable named unique_scenario_types containing sorted unique strings.",
        )

        # Strictly serial: the Gemma call begins only after Coder returns or fails.
        code_started = perf_counter()
        try:
            draft = await worker.draft(task, research_id=run_id)
            code_outcome: dict[str, object] = {
                "success": True,
                "draft": draft.model_dump(),
                "latency_ms": (perf_counter() - code_started) * 1000,
            }
        except Exception as exc:
            code_outcome = {
                "success": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "latency_ms": (perf_counter() - code_started) * 1000,
            }

        chat_system = (
            "You are a bounded warning summarizer. Return one short sentence only. "
            "Do not calculate or quote financial numbers, do not recommend a trade, "
            "and do not claim facts outside the supplied Java warning text."
        )
        chat_payload = {
            "selected_model": compact.selected_model,
            "material_warnings": compact.material_warnings,
        }
        chat_started = perf_counter()
        try:
            completion = await router.complete(
                [
                    {"role": "system", "content": chat_system},
                    {"role": "user", "content": json.dumps(chat_payload)},
                ],
                temperature=0,
                max_tokens=128,
                route_hint="chat",
            )
            chat_outcome: dict[str, object] = {
                "success": bool(completion.content.strip()),
                "content": completion.content.strip() or None,
                "route": completion.route,
                "model": completion.model,
                "latency_ms": completion.latency_ms,
            }
        except Exception as exc:
            chat_outcome = {
                "success": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "latency_ms": (perf_counter() - chat_started) * 1000,
            }

        print(
            json.dumps(
                {
                    "event": "phase1b_coder_gemma_capability_probe",
                    "run_id": run_id,
                    "strict_serial_order": ["code", "chat"],
                    "java_observation": {
                        "symbol": compact.symbol,
                        "selected_model": compact.selected_model,
                        "material_warnings": compact.material_warnings,
                    },
                    "coder_task": task.model_dump(),
                    "coder": code_outcome,
                    "gemma_system_prompt": chat_system,
                    "gemma_payload": chat_payload,
                    "gemma": chat_outcome,
                    "total_latency_ms": (perf_counter() - started) * 1000,
                    "coder_executed": False,
                    "valuation_report_modified": False,
                },
                ensure_ascii=False,
                default=str,
            )
        )
    finally:
        await stock.aclose()
        await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
