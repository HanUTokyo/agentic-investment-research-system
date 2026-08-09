"""Opt-in raw Coder response capture after a typed CodeDraft protocol failure."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.clients import RouterClient
from app.config import get_settings
from app.contracts import CodeTask


async def main() -> None:
    router = RouterClient(get_settings())
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
    try:
        completion = await router.complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Return JSON only with code, explanation, assumptions. Generate a bounded "
                        "Python draft only. Do not use imports, files, network, shell, DCF formulas, "
                        "or tool-call syntax. Use only named variables and available methods."
                    ),
                },
                {"role": "user", "content": task.model_dump_json()},
            ],
            temperature=0,
            max_tokens=512,
            route_hint="code",
        )
        print(
            json.dumps(
                {
                    "event": "coder_raw_protocol_probe",
                    "run_id": str(uuid4()),
                    "route_hint": "code",
                    "task": task.model_dump(),
                    "http_success": True,
                    "model": completion.model,
                    "route": completion.route,
                    "latency_ms": completion.latency_ms,
                    "raw_content": completion.content,
                    "executed": False,
                },
                ensure_ascii=False,
            )
        )
    finally:
        await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
