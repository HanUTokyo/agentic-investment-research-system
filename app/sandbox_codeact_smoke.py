"""An intentionally harmless, container-only NOOA CodeAct smoke test."""

import asyncio
import hashlib
import json
from typing import Any

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy

from app.clients import StockPlatformClient
from app.config import get_settings
from app.llm import build_nooa_router_llm


class AuditedCodeActStrategy(CodeActStrategy):
    """Smoke-only audit hook: record metadata, never generated source text."""

    async def _execute_code(
        self,
        runtime: Any,
        code: str,
        builtins: dict[str, Any],
        session: Any,
        target_method_name: str,
        tool_call_id: str | None = None,
    ) -> Any:
        result = await super()._execute_code(
            runtime, code, builtins, session, target_method_name, tool_call_id
        )
        print(
            json.dumps(
                {
                    "event": "sandbox_codeact_execution",
                    "method": target_method_name,
                    "iteration": session.iteration,
                    "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                    "code_bytes": len(code.encode()),
                    "status": "error" if result.error else "complete",
                    "returned_value_type": type(result.returned_value).__name__,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return result


class ArithmeticSmokeAgent(Agent):
    @strategy(
        AuditedCodeActStrategy(
            config=CodeActConfig(max_iterations=2, max_retries=1, max_tokens=128)
        )
    )
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

    @strategy(
        AuditedCodeActStrategy(
            config=CodeActConfig(max_iterations=2, max_retries=1, max_tokens=128)
        )
    )
    async def inspect(self, task: str) -> str:
        """Use the provided deterministic method and return the exact engine version only."""
        ...


async def main() -> None:
    settings = get_settings()
    agent = ArithmeticSmokeAgent(llm=build_nooa_router_llm(settings, route_hint="code"))
    result = await agent.solve("Use Python to calculate 17 * 25 + 8. Return only the integer.")
    stock_client = StockPlatformClient(settings)
    try:
        valuation_agent = ValuationToolSmokeAgent(
            stock_client, llm=build_nooa_router_llm(settings, route_hint="code")
        )
        engine_version = await valuation_agent.inspect(
            "Call get_engine_version with AAPL. Return the exact result only."
        )
    finally:
        await stock_client.aclose()
    print({"codeact_arithmetic_result": result, "codeact_java_tool_result": engine_version})


if __name__ == "__main__":
    asyncio.run(main())
