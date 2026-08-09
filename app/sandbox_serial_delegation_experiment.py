"""Run the real four-model, strictly serial synthetic delegation experiment."""

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.agents.delegation_controller import SerialDelegationController
from app.clients import RouterClient
from app.config import get_settings
from app.llm import build_nooa_controller_llm


async def main() -> None:
    settings = get_settings()
    run_id = str(uuid4())
    router = RouterClient(settings)
    controller = SerialDelegationController(router, llm=build_nooa_controller_llm(settings))
    started = perf_counter()
    try:
        result = await asyncio.wait_for(
            controller.solve(
                "Solve and explain 17 * 25 + 8. Delegate reasoning, then code, then chat; "
                "integrate their successful outputs."
            ),
            timeout=1_050,
        )
        outcome: dict[str, object] = {"success": True, "result": result.model_dump()}
    except Exception as exc:
        outcome = {"success": False, "error_type": type(exc).__name__, "error": str(exc)[:500]}
    finally:
        await router.aclose()
    print(
        json.dumps(
            {
                "event": "serial_delegation_experiment",
                "run_id": run_id,
                "started_at": datetime.now(UTC).isoformat(),
                "latency_ms": (perf_counter() - started) * 1000,
                "worker_trace": [item.model_dump() for item in controller.worker_trace],
                **outcome,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
