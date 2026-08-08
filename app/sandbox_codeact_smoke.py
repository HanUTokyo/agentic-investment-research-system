"""An intentionally harmless, container-only NOOA CodeAct smoke test."""

import asyncio
from typing import Any

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy

from app.clients import StockPlatformClient
from app.config import get_settings
from app.llm import build_nooa_router_llm


class ArithmeticSmokeAgent(Agent):
    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5, max_retries=1)))
    async def solve(self, task: str) -> int:
        """Use Python to calculate the requested arithmetic and return the integer only."""
        ...


class ValuationToolSmokeAgent(Agent):
    def __init__(self, stock_client: StockPlatformClient, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stock_client = stock_client

    async def get_engine_version(self, symbol: str) -> str:
        """Return the authoritative Java valuation engine version for a tracked symbol."""
        return (await self._stock_client.get_current_valuation(symbol)).engine_version

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5, max_retries=1)))
    async def inspect(self, task: str) -> str:
        """Use the provided deterministic method and return the exact engine version only."""
        ...


async def main() -> None:
    settings = get_settings()
    agent = ArithmeticSmokeAgent(llm=build_nooa_router_llm(settings))
    result = await agent.solve("Use Python to calculate 17 * 25 + 8. Return only the integer.")
    stock_client = StockPlatformClient(settings)
    try:
        valuation_agent = ValuationToolSmokeAgent(stock_client, llm=build_nooa_router_llm(settings))
        engine_version = await valuation_agent.inspect(
            "Call get_engine_version with AAPL. Return the exact result only."
        )
    finally:
        await stock_client.aclose()
    print({"codeact_arithmetic_result": result, "codeact_java_tool_result": engine_version})


if __name__ == "__main__":
    asyncio.run(main())
