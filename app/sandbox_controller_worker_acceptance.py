"""Opt-in real Architecture B acceptance: controller with optional code worker."""

import asyncio
import json

from app.agents import ValuationAgent
from app.clients import RouterClient, StockPlatformClient
from app.config import get_settings
from app.llm import build_nooa_controller_llm
from app.workers import RouterCodeWorker


async def main() -> None:
    settings = get_settings()
    stock, router = StockPlatformClient(settings), RouterClient(settings)
    try:
        worker = RouterCodeWorker(router)
        agent = ValuationAgent(
            stock,
            code_worker=worker,
            llm=build_nooa_controller_llm(settings),
        )
        report = await agent.investigate(
            "Compare available valuation scenarios. Use draft_python only if a bounded Python "
            "transformation is useful; otherwise use deterministic tools directly.",
            "AAPL",
        )
        print(
            json.dumps(
                {
                    "report": report.model_dump(mode="json"),
                    "code_worker_traces": [item.model_dump(mode="json") for item in worker.traces],
                },
                ensure_ascii=False,
            )
        )
    finally:
        await stock.aclose()
        await router.aclose()


if __name__ == "__main__":
    asyncio.run(main())
