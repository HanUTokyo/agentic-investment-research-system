"""Strictly serial latency sanity check for the evidence-sufficiency decision.

This runner changes no model prompt, schema, fixture, retry policy, or agent
logic. It only repeats the two existing conditions in a caller-selected order
and records the narrow controller-call interval separately from setup and
deterministic validation.
"""

from __future__ import annotations

import asyncio
import json
import os
from statistics import mean, median
from typing import Any

from app.evaluation.four_way import validate_public_synthetic_artifact
from app.sandbox_evidence_sufficiency_evaluation import run_evidence_sufficiency_pattern

_CONDITIONS = {
    "A": ("ministral_only", False),
    "B": ("ministral_router_advisory", True),
}


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[float]] = {}
    for item in results:
        by_condition.setdefault(str(item["condition"]), []).append(float(item["total_latency_ms"]))

    def describe(values: list[float]) -> dict[str, float | int]:
        return {
            "n": len(values),
            "min_ms": min(values),
            "max_ms": max(values),
            "mean_ms": mean(values),
            "median_ms": median(values),
        }

    first = [float(item["total_latency_ms"]) for item in results if item["sequence_position"] == 1]
    non_first = [
        float(item["total_latency_ms"]) for item in results if item["sequence_position"] != 1
    ]
    return {
        "by_condition": {name: describe(values) for name, values in by_condition.items()},
        "position_summary": {
            "first_position": describe(first),
            "non_first_position": describe(non_first),
        },
    }


async def main() -> None:
    sequence_id = os.getenv("LATENCY_SEQUENCE_ID", "sequence-1")
    tokens = [
        item.strip().upper() for item in os.getenv("LATENCY_SEQUENCE", "A,B,A,B,A,B").split(",")
    ]
    if not tokens or any(item not in _CONDITIONS for item in tokens):
        raise ValueError("LATENCY_SEQUENCE must contain only comma-separated A and B values")

    results: list[dict[str, Any]] = []
    previous_controller_finished_at: float | None = None
    for position, token in enumerate(tokens, start=1):
        condition, with_router = _CONDITIONS[token]
        result = await asyncio.wait_for(
            run_evidence_sufficiency_pattern(
                condition,
                with_router=with_router,
                sequence_id=sequence_id,
                sequence_position=position,
                previous_controller_finished_at=previous_controller_finished_at,
            ),
            timeout=900,
        )
        previous_controller_finished_at = result.pop("_last_controller_finished_at", None)
        results.append(result)

    artifact = {
        "event": "phase1_evidence_sufficiency_latency_diagnostic",
        "case": "synthetic-aapl-phase1b-v1",
        "sequence_id": sequence_id,
        "sequence": tokens,
        "controls": {
            "strict_serial_execution": True,
            "fixture": "fixtures/eval/phase1b_aapl.json",
            "prompt_schema_retry_policy": "unchanged_from_evidence_sufficiency_run",
            "router_delegation": "not_intentionally_requested",
            "market_information_access": False,
            "web_access": False,
            "serving_stack_reset": os.getenv("LATENCY_SERVING_RESET", "not_performed"),
            "backend_load_prompt_eval_generation_metrics": "unavailable_from_current_backend_response",
        },
        "results": results,
        "summary": _summary(results),
    }
    validate_public_synthetic_artifact(artifact)
    rendered = json.dumps(artifact, ensure_ascii=False, default=str)
    if output_path := os.getenv("EVAL_OUTPUT_PATH"):
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    asyncio.run(main())
