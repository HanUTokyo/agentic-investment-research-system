"""Verify the Router path from the same restricted NOOA sandbox."""

from __future__ import annotations

import asyncio
import json
from time import perf_counter

from app.clients import RouterClient
from app.config import get_settings


async def main() -> None:
    router = RouterClient(get_settings())
    try:
        started = perf_counter()
        ready = await router.readiness()
        health_latency_ms = (perf_counter() - started) * 1000

        started = perf_counter()
        route = await router.route("Explain the strategy for adding 17 and 25.")
        route_latency_ms = (perf_counter() - started) * 1000

        started = perf_counter()
        chat = await router.complete(
            [{"role": "user", "content": "Reply with the word connected."}],
            route_hint="chat",
            temperature=0,
            max_tokens=32,
        )
        chat_latency_ms = (perf_counter() - started) * 1000

        started = perf_counter()
        reason = await router.complete(
            [{"role": "user", "content": "What is 17 * 25 + 8? Reply with the number only."}],
            route_hint="reason",
            temperature=0,
            max_tokens=1024,
        )
        reason_latency_ms = (perf_counter() - started) * 1000

        print(
            json.dumps(
                {
                    "event": "sandbox_router_connectivity_probe",
                    "health_ready": ready,
                    "health_latency_ms": health_latency_ms,
                    "route": route.model_dump(),
                    "route_latency_ms": route_latency_ms,
                    "chat": {
                        "route": chat.route,
                        "model": chat.model,
                        "content": chat.content,
                        "content_empty": not bool(chat.content.strip()),
                        "latency_ms": chat_latency_ms,
                    },
                    "reason": {
                        "route": reason.route,
                        "model": reason.model,
                        "content": reason.content,
                        "content_empty": not bool(reason.content.strip()),
                        "latency_ms": reason_latency_ms,
                    },
                    "success": ready
                    and bool(chat.content.strip())
                    and bool(reason.content.strip()),
                },
                ensure_ascii=False,
            )
        )
    finally:
        await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
