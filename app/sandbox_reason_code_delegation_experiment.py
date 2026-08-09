"""Real Stage 2: Ministral -> R1 -> Coder -> Ministral native return_result."""

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
        result = await asyncio.wait_for(controller.solve_reason_code(), timeout=960)
        strict = (
            len(controller.worker_trace) == 2
            and [item.route_hint for item in controller.worker_trace] == ["reason", "code"]
            and all(item.ok for item in controller.worker_trace)
            and result.code_draft_trusted is False
            and result.verification_source == "deterministic_expression"
            and result.final_answer == "433"
        )
        outcome: dict[str, object] = {
            "success": strict,
            "result": result.model_dump(),
            "acceptance_error": None if strict else "worker_failure_or_wrong_sequence",
        }
    except Exception as exc:
        outcome = {"success": False, "error_type": type(exc).__name__, "error": str(exc)[:500]}
    finally:
        await router.aclose()
    print(
        json.dumps(
            {
                "event": "reason_code_delegation_experiment",
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
