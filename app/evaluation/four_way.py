"""Four-way Phase 1B model evaluation primitives.

The harness deliberately keeps financial facts and report materialization in the
existing valuation agent.  Only model invocation differs across conditions.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.agents.valuation_projection import CompactValuationObservation
from app.clients.ai_router import RouterClient
from app.clients.errors import UpstreamProtocolError
from app.contracts import (
    CodeDraft,
    CodeTask,
    ReasonResult,
    ValuationEvaluation,
    ValuationSnapshot,
    WorkerResult,
)
from app.tools import validate_code_draft

_PRIVATE_TRACE_MARKERS = ("/Users/", "file://", "Bearer ", "sk-", "postgres://")


def validate_public_synthetic_artifact(payload: dict[str, Any]) -> None:
    """Reject obvious private paths, credentials, and non-synthetic case identifiers."""
    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if payload.get("case") != "synthetic-aapl-phase1b-v1":
        raise ValueError("evaluation artifact must identify the frozen synthetic case")
    if marker := next((item for item in _PRIVATE_TRACE_MARKERS if item in rendered), None):
        raise ValueError(f"evaluation artifact contains prohibited marker: {marker}")


@dataclass
class FrozenValuationClient:
    """A read-only Java-derived case source used identically by every condition."""

    valuation: ValuationSnapshot
    evaluation: ValuationEvaluation

    @classmethod
    def from_path(cls, path: Path) -> tuple[FrozenValuationClient, str]:
        payload = json.loads(path.read_text())
        return (
            cls(
                valuation=ValuationSnapshot.model_validate(payload["valuation"]),
                evaluation=ValuationEvaluation.model_validate(payload["scenarioEvaluation"]),
            ),
            str(payload["question"]),
        )

    async def get_current_valuation(self, _symbol: str) -> ValuationSnapshot:
        return self.valuation

    async def run_valuation_scenario(
        self, _symbol: str, _scenario_type: str, _assumptions: dict[str, Any] | None = None
    ) -> ValuationEvaluation:
        return self.evaluation

    async def get_company_snapshot(self, _symbol: str) -> Any:
        raise RuntimeError("not available in four-way valuation evaluation")

    async def get_financial_history(self, _symbol: str) -> Any:
        raise RuntimeError("not available in four-way valuation evaluation")

    async def solve_market_implied_assumptions(self, _symbol: str) -> None:
        return None


@dataclass
class RawCall:
    stage: str
    model: str
    prompt: list[dict[str, Any]]
    response: str | None
    latency_ms: float
    success: bool
    error_type: str | None = None


class DirectStructuredClient:
    """Strict direct HTTP structured generation: no fence stripping or repair."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/", timeout=timeout_seconds
        )
        self._owns_client = client is None
        self.model = model
        self._timeout_seconds = timeout_seconds
        self.calls: list[RawCall] = []

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def generate(
        self, stage: str, messages: list[dict[str, Any]], schema: type[BaseModel]
    ) -> Any:
        started = perf_counter()
        content: str | None = None
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._client.post(
                    "chat/completions",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0,
                        "max_tokens": 768,
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema.__name__,
                                "schema": schema.model_json_schema(),
                            },
                        },
                    },
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise UpstreamProtocolError("direct model returned empty content")
            parsed = json.loads(content)
            result = schema.model_validate(parsed)
        except Exception as exc:
            self.calls.append(
                RawCall(
                    stage,
                    self.model,
                    messages,
                    content,
                    (perf_counter() - started) * 1000,
                    False,
                    type(exc).__name__,
                )
            )
            raise
        self.calls.append(
            RawCall(stage, self.model, messages, content, (perf_counter() - started) * 1000, True)
        )
        return result


@dataclass
class WorkerBundle:
    """Evaluation-only serial Router worker collector; all results remain advisory."""

    router: RouterClient
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def collect(
        self, compact: CompactValuationObservation, question: str, _trace_id: str
    ) -> tuple[ReasonResult | None, list[dict[str, Any]]]:
        reason = await self._plain_worker(
            "reason",
            "Return one non-numerical evidence gap only. Do not call tools or quote values.",
            f"Question: {question}\nWarnings: {compact.material_warnings}",
        )
        code = await self._code_worker()
        await self._plain_worker(
            "chat",
            "Return one short non-numerical warning summary only. Do not recommend a trade.",
            json.dumps({"warnings": compact.material_warnings}),
        )
        reason_result = ReasonResult(worker=reason, proposal=reason.content) if reason else None
        return reason_result, [item for item in [self.calls[-3], code, self.calls[-1]]]

    async def _plain_worker(
        self, route: Literal["reason", "chat"], system: str, user: str
    ) -> WorkerResult:
        started = perf_counter()
        try:
            completion = await self.router.complete(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                max_tokens=512 if route == "reason" else 128,
                route_hint=route,
            )
            content = completion.content.strip()
            result = WorkerResult(
                ok=bool(content),
                http_success=True,
                content_empty=not bool(content),
                content=content or None,
                error_type=None if content else "empty_content",
                latency_ms=completion.latency_ms,
                route_hint=route,
                model=completion.model,
            )
        except Exception as exc:
            result = WorkerResult(
                ok=False,
                http_success=False,
                content_empty=True,
                error_type=type(exc).__name__,
                latency_ms=(perf_counter() - started) * 1000,
                route_hint=route,
            )
        self.calls.append({"worker": route, **result.model_dump()})
        return result

    async def _code_worker(self) -> dict[str, Any]:
        task = CodeTask(
            objective="Create sorted unique scenario type strings only.",
            known_variables={"scenario_types": "list[str]"},
            constraints=["No imports, files, network, shell, DCF, price, or return calculations."],
            expected_result="unique_scenario_types derived only from scenario_types.",
        )
        started = perf_counter()
        try:
            completion = await self.router.complete(
                [
                    {
                        "role": "system",
                        "content": "Return JSON only with code, explanation, assumptions.",
                    },
                    {"role": "user", "content": task.model_dump_json()},
                ],
                temperature=0,
                max_tokens=512,
                route_hint="code",
            )
            raw_content = completion.content
            if not raw_content.strip():
                raise UpstreamProtocolError("code worker returned empty content")
            payload = json.loads(raw_content)
            draft = CodeDraft.model_validate(payload)
            validate_code_draft(draft.code)
            result: dict[str, Any] = {
                "worker": "code",
                "ok": True,
                "content_empty": False,
                "latency_ms": completion.latency_ms,
                "draft": draft.model_dump(),
                "raw_content": raw_content,
                "executed": False,
            }
        except Exception as exc:
            result = {
                "worker": "code",
                "ok": False,
                "content_empty": False,
                "error_type": type(exc).__name__,
                "latency_ms": (perf_counter() - started) * 1000,
                "raw_content": locals().get("raw_content"),
                "executed": False,
            }
        self.calls.append(result)
        return result
