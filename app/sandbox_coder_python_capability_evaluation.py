"""Opt-in, real local-coder Python capability evaluation; never production runtime."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.clients import RouterClient
from app.config import get_settings
from app.evaluation.coder_python import (
    DirectOllamaCoderCompletionClient,
    RouterCoderCompletionClient,
    load_cases,
    run_case,
)

_ROOT = Path(__file__).resolve().parents[1]
_DATASET = _ROOT / "eval" / "datasets" / "coder_python_cases.json"


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    temporary.replace(path)


async def main() -> None:
    run_id = f"coder-python-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    output = _ROOT / "artifacts" / f"coder_python_capability_{run_id}"
    requested_case_id = os.getenv("CODER_PYTHON_CASE_ID")
    repeat_count = int(os.getenv("CODER_PYTHON_REPEAT_COUNT", "1"))
    if not 1 <= repeat_count <= 5:
        raise ValueError("CODER_PYTHON_REPEAT_COUNT must be between 1 and 5")
    direct_base_url = os.getenv("CODER_PYTHON_DIRECT_OLLAMA_BASE_URL")
    direct_model = os.getenv("CODER_PYTHON_DIRECT_OLLAMA_MODEL", "deepseek-coder:6.7b")
    router: RouterClient | None = None
    direct_client: DirectOllamaCoderCompletionClient | None = None
    if direct_base_url is not None:
        direct_client = DirectOllamaCoderCompletionClient(direct_base_url, direct_model)
        client = direct_client
    else:
        router = RouterClient(get_settings())
        client = RouterCoderCompletionClient(router)
    started = perf_counter()
    records: list[dict[str, object]] = []
    try:
        cases = tuple(
            case for case in load_cases(_DATASET) if requested_case_id in {None, case.case_id}
        )
        if not cases:
            raise ValueError("CODER_PYTHON_CASE_ID does not identify a dataset case")
        for case in cases:
            for attempt in range(1, repeat_count + 1):
                try:
                    record: dict[str, object] = await run_case(client, case)
                except Exception as exc:
                    record = {
                        "case_id": case.case_id,
                        "passed": False,
                        "static_valid": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:1_000],
                    }
                record["attempt"] = attempt
                records.append(record)
                _write_json_atomic(
                    output / f"{len(records):02d}_{case.case_id}_{attempt}.json", record
                )
    finally:
        if router is not None:
            await router.aclose()
        elif direct_client is not None:
            await direct_client.aclose()
    _write_json_atomic(
        output / "summary.json",
        {
            "run_id": run_id,
            "dataset": str(_DATASET.relative_to(_ROOT)),
            "case_count": len(records),
            "requested_case_id": requested_case_id,
            "repeat_count": repeat_count,
            "passed_count": sum(bool(record.get("passed")) for record in records),
            "static_valid_count": sum(bool(record.get("static_valid")) for record in records),
            "total_latency_ms": (perf_counter() - started) * 1_000,
            "execution_boundary": "no-network, read-only Docker sandbox; model code never runs on host",
            "condition": (
                "direct_ollama_capability_only"
                if direct_base_url is not None
                else "router_code_route"
            ),
            "requested_model": direct_model if direct_base_url is not None else None,
        },
    )
    print(json.dumps({"artifact_dir": str(output), "case_count": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
