"""An intentionally harmless, container-only NOOA CodeAct smoke test."""

import asyncio

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy

from app.config import get_settings
from app.llm import build_nooa_router_llm


class ArithmeticSmokeAgent(Agent):
    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=5, max_retries=1)))
    async def solve(self, task: str) -> str:
        """Use Python to calculate the requested arithmetic and return the integer only."""
        ...


async def main() -> None:
    settings = get_settings()
    agent = ArithmeticSmokeAgent(llm=build_nooa_router_llm(settings))
    result = await agent.solve("Use Python to calculate 17 * 25 + 8. Return only the integer.")
    print({"codeact_result": result})


if __name__ == "__main__":
    asyncio.run(main())
