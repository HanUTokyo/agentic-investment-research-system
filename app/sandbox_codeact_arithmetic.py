"""Run the deterministic, side-effect-free CodeAct sandbox audit smoke test."""

import asyncio

from app.config import get_settings
from app.llm import build_nooa_router_llm
from app.sandbox_codeact_smoke import ArithmeticSmokeAgent


async def main() -> None:
    agent = ArithmeticSmokeAgent(llm=build_nooa_router_llm(get_settings()))
    result = await agent.solve("Use Python to calculate 17 * 25 + 8. Return only the integer.")
    print({"event": "sandbox_codeact_smoke_result", "result": result})


if __name__ == "__main__":
    asyncio.run(main())
