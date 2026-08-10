"""Phase 1 close-out: valuation-gap evidence vs. missing market information.

Two serial conditions share the frozen public AAPL compact valuation.  Neither
condition has market-data access; the Router condition adds only untrusted local
reasoning, never an information source.
"""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from nooa.events import Error, LLMOutput, Task

from app.agents import ConstrainedTypedValuationAgent
from app.agents.valuation_grounding import (
    unsupported_causal_claims,
    unsupported_numerical_text_claims,
)
from app.agents.valuation_projection import CompactScenarioObservation
from app.clients import RouterClient
from app.config import get_settings
from app.contracts import ReasonResult
from app.evaluation.four_way import FrozenValuationClient, validate_public_synthetic_artifact
from app.llm import build_nooa_controller_llm

CASE_PATH = Path("/sandbox/fixtures/eval/phase1b_aapl.json")


class RawNooaTrace:
    """Synthetic-only prompt/completion capture for human audit."""

    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def attach(self, event_manager: Any) -> None:
        event_manager.on("*", self._on_event)

    def _on_event(self, event: Any) -> None:
        if isinstance(event, Task):
            self.events.append({"type": "prompt", "content": event.prompt})
        elif isinstance(event, LLMOutput):
            self.events.append({"type": "completion", "content": event.content})
        elif isinstance(event, Error):
            self.events.append({"type": "validation_error", "content": event.content})


def _allowed_numbers(compact: Any) -> set[Decimal]:
    values = {compact.current_price, compact.bear_value, compact.base_value, compact.bull_value}
    return {value for value in values if isinstance(value, Decimal)}


async def _run_pattern(name: str, *, with_router: bool) -> dict[str, Any]:
    settings = get_settings()
    data, question = FrozenValuationClient.from_path(CASE_PATH)
    router = RouterClient(settings) if with_router else None
    agent = ConstrainedTypedValuationAgent(
        data,
        reasoning_client=router,
        llm=build_nooa_controller_llm(settings),
    )
    raw_trace = RawNooaTrace()
    raw_trace.attach(agent.event_manager)
    started = perf_counter()
    decisions: list[dict[str, Any]] = []
    controller_causal: list[str] = []
    controller_numerical: list[str] = []
    reason: ReasonResult | None = None
    scenario: CompactScenarioObservation | None = None
    lifecycle_state = "START"
    try:
        compact = await agent.get_compact_valuation("AAPL")
        lifecycle_state = "EVIDENCE_COLLECTED"
        allowed_numbers = _allowed_numbers(compact)
        for iteration in range(1, 4):
            context = agent.build_decision_context(
                question,
                compact,
                scenario,
                reason,
                agent.decision_state(scenario, reason),
            )
            decision = await agent.decide_evidence_sufficiency(context)
            decisions.append({"iteration": iteration, **decision.model_dump(mode="json")})
            controller_causal.extend(unsupported_causal_claims(decision.reason))
            controller_numerical.extend(
                unsupported_numerical_text_claims(decision.reason, allowed_numbers)
            )
            if decision.action == "REQUEST_EVIDENCE":
                lifecycle_state = "REQUESTED_MARKET_INFORMATION"
                break
            if decision.action == "FINALIZE":
                lifecycle_state = "INVALID_FINALIZE_WITH_INFORMATION_DEFICIT"
                break
            result = await agent.dispatch_decision(decision, "AAPL", compact, reason, scenario)
            if isinstance(result, ReasonResult):
                reason = result
            elif isinstance(result, CompactScenarioObservation):
                scenario = result
        else:
            lifecycle_state = "BOUNDED_LOOP_EXHAUSTION"

        final = decisions[-1] if decisions else None
        advisory_causal = [
            claim
            for advisory in agent.advisory_results
            for claim in unsupported_causal_claims(advisory.content or "")
        ]
        passed = bool(
            final
            and final["action"] == "REQUEST_EVIDENCE"
            and final.get("evidence_type") == "MARKET_INFORMATION"
            and not controller_causal
            and not controller_numerical
            and lifecycle_state == "REQUESTED_MARKET_INFORMATION"
        )
        return {
            "condition": name,
            "success": passed,
            "total_latency_ms": (perf_counter() - started) * 1000,
            "question": question,
            "evidence_sufficiency_decision": final,
            "requested_evidence_type": final.get("evidence_type") if final else None,
            "typed_schema_valid": True,
            "final_lifecycle_state": lifecycle_state,
            "unsupported_causal_claims": controller_causal,
            "unsupported_numerical_claims": controller_numerical,
            "delegation_count": len(agent.advisory_results),
            "selected_worker_or_router_trace": [
                item.model_dump(mode="json") for item in agent.advisory_results
            ],
            "advisory_unsupported_causal_claims": advisory_causal,
            "scenario_calls": agent.scenario_call_count,
            "raw_trace": raw_trace.events,
            "decisions": decisions,
        }
    except Exception as exc:
        return {
            "condition": name,
            "success": False,
            "total_latency_ms": (perf_counter() - started) * 1000,
            "question": question,
            "typed_schema_valid": False,
            "final_lifecycle_state": lifecycle_state,
            "error_type": type(exc).__name__,
            "error": str(exc)[:1_000],
            "unsupported_causal_claims": controller_causal,
            "unsupported_numerical_claims": controller_numerical,
            "delegation_count": len(agent.advisory_results),
            "selected_worker_or_router_trace": [
                item.model_dump(mode="json") for item in agent.advisory_results
            ],
            "raw_trace": raw_trace.events,
            "decisions": decisions,
        }
    finally:
        if router is not None:
            await router.aclose()


async def main() -> None:
    conditions = {
        "ministral_only": lambda: _run_pattern("ministral_only", with_router=False),
        "ministral_router_advisory": lambda: _run_pattern(
            "ministral_router_advisory", with_router=True
        ),
    }
    selected = os.getenv("EVIDENCE_SUFFICIENCY_CONDITION")
    if selected and selected not in conditions:
        raise ValueError(f"unknown EVIDENCE_SUFFICIENCY_CONDITION: {selected}")
    names = [selected] if selected else list(conditions)
    results = [await asyncio.wait_for(conditions[name](), timeout=900) for name in names]
    artifact = {
        "event": "phase1_evidence_sufficiency_evaluation",
        "case": "synthetic-aapl-phase1b-v1",
        "controls": {
            "market_information_access": False,
            "web_access": False,
            "router_route_hint": None,
            "strict_serial_execution": True,
        },
        "results": results,
    }
    validate_public_synthetic_artifact(artifact)
    rendered = json.dumps(artifact, ensure_ascii=False, default=str)
    if output_path := os.getenv("EVAL_OUTPUT_PATH"):
        Path(output_path).write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    asyncio.run(main())
