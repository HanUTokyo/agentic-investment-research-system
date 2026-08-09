"""Opt-in real Architecture A acceptance: Gemma controller -> NOOA -> Java."""

import asyncio
import json

from app.agents import ValuationAgent
from app.clients import StockPlatformClient
from app.config import get_settings
from app.llm import build_nooa_controller_llm


async def main() -> None:
    settings = get_settings()
    stock = StockPlatformClient(settings)
    try:
        agent = ValuationAgent(stock, llm=build_nooa_controller_llm(settings))
        report = await agent.investigate(
            "Retrieve the current valuation and explain the main valuation warning.", "AAPL"
        )
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False))
    finally:
        await stock.aclose()


if __name__ == "__main__":
    asyncio.run(main())
