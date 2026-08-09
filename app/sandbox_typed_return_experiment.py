"""Opt-in real, serial Gemma/NOOA typed-return schema complexity experiment."""

import asyncio
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import cast

from app.config import get_settings
from app.experiments.typed_return_schema import LEVEL_METHODS, TypedReturnExperimentAgent, run_level
from app.llm import build_nooa_controller_llm

RUNS_PER_LEVEL = int(os.environ.get("TYPED_RETURN_RUNS_PER_LEVEL", "20"))
OUTPUT = Path("/tmp/nooa-typed-return-gemma.jsonl")  # noqa: S108 - explicit opt-in trace


async def main() -> None:
    settings = get_settings()
    rows: list[dict[str, object]] = []
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("a") as output:
        for level in LEVEL_METHODS:
            for run_index in range(RUNS_PER_LEVEL):
                agent = TypedReturnExperimentAgent(level, llm=build_nooa_controller_llm(settings))
                trace = await run_level(agent, level)
                row = {"run": run_index + 1, **trace.as_json()}
                rows.append(row)
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                print(json.dumps(row, ensure_ascii=False), flush=True)
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["level"])].append(row)
    for level, group in grouped.items():
        total = len(group)
        native = sum(bool(row["native_return_called"]) for row in group)
        valid = sum(
            bool(row["native_return_called"])
            and not bool(row["schema_validation_failed"])
            and not bool(row["markdown_or_text"])
            for row in group
        )
        print(
            json.dumps(
                {
                    "summary": level,
                    "native_return_result_rate": native / total,
                    "schema_valid_return_rate": valid / total,
                    "markdown_instead_of_tool_rate": sum(
                        bool(row["markdown_or_text"]) for row in group
                    )
                    / total,
                    "empty_result_rate": sum(bool(row["empty_result"]) for row in group) / total,
                    "timeout_rate": sum(bool(row["timeout"]) for row in group) / total,
                    "mean_latency_ms": sum(float(cast(float, row["latency_ms"])) for row in group)
                    / total,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
