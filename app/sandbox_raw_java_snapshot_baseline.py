"""Run one direct, free-form full-Java-snapshot baseline on a synthetic case."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from time import perf_counter

from app.config import get_settings
from app.evaluation.four_way import DirectTextClient

CASE_PATH = Path("/sandbox/fixtures/eval/phase1b_aapl.json")


def build_messages(payload: dict[str, object], *, concise: bool = False) -> list[dict[str, str]]:
    question = str(payload["question"])
    raw_java_outputs = {
        "GET /api/valuations/AAPL": payload["valuation"],
        "POST /api/valuations/AAPL/evaluate (predefined BULL scenario)": payload[
            "scenarioEvaluation"
        ],
    }
    return [
        {
            "role": "system",
            "content": (
                "You are an investment research analyst. The user message contains a question and "
                "complete deterministic Java valuation API outputs. Answer directly in concise prose. "
                "Do not calculate, alter, or invent financial numbers. Every numerical claim must be "
                "present in the supplied Java JSON. Identify the most important uncertainty."
                + (
                    " Use at most 120 words in two complete paragraphs; finish every sentence."
                    if concise
                    else ""
                )
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"question": question, "java_api_outputs": raw_java_outputs},
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


async def main() -> None:
    payload = json.loads(CASE_PATH.read_text())
    settings = get_settings()
    model = os.environ["RAW_SNAPSHOT_MODEL"]
    client = DirectTextClient(
        base_url=str(settings.ministral_controller_base_url),
        model=model,
        timeout_seconds=settings.http_timeout_seconds,
        max_tokens=int(os.getenv("RAW_SNAPSHOT_MAX_TOKENS", "768")),
    )
    started = perf_counter()
    try:
        answer = await client.generate(
            build_messages(payload, concise=os.getenv("RAW_SNAPSHOT_CONCISE", "") == "1")
        )
        result: dict[str, object] = {
            "event": "raw_java_snapshot_baseline",
            "case": payload["caseId"],
            "model": model,
            "success": True,
            "latency_ms": (perf_counter() - started) * 1000,
            "raw_calls": [call.__dict__ for call in client.calls],
            "final_text": answer,
        }
    except Exception as exc:
        result = {
            "event": "raw_java_snapshot_baseline",
            "case": payload["caseId"],
            "model": model,
            "success": False,
            "latency_ms": (perf_counter() - started) * 1000,
            "raw_calls": [call.__dict__ for call in client.calls],
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
    finally:
        await client.aclose()
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
