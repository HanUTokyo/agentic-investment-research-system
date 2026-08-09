"""Real minimal chain: Ministral -> R1 -> Ministral native return_result."""

import asyncio
import json
from time import perf_counter
from uuid import uuid4

from app.agents.delegation_controller import SerialDelegationController
from app.clients import RouterClient
from app.config import get_settings
from app.llm import build_nooa_controller_llm


async def main() -> None:
    settings = get_settings()
    router = RouterClient(settings)
    controller = SerialDelegationController(router, llm=build_nooa_controller_llm(settings))
    started = perf_counter()
    try:
        result = await asyncio.wait_for(controller.solve_reason_only(), timeout=720)
        strict_worker_success = len(controller.worker_trace) == 1 and controller.worker_trace[0].ok
        outcome: dict[str, object] = {
            "success": strict_worker_success,
            "result": result.model_dump(),
            "acceptance_error": None if strict_worker_success else "worker_failure_or_retry",
        }
    except Exception as exc:
        outcome = {"success": False, "error_type": type(exc).__name__, "error": str(exc)[:500]}
    finally:
        await router.aclose()
    print(
        json.dumps(
            {
                "event": "reason_delegation_experiment",
                "run_id": str(uuid4()),
                "latency_ms": (perf_counter() - started) * 1000,
                "worker_trace": [item.model_dump() for item in controller.worker_trace],
                **outcome,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
