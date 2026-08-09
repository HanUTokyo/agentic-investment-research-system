"""Run the four Phase 1B conditions once, strictly serially, on a frozen case."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from nooa.events import Error, LLMOutput, Task

from app.agents import ConstrainedTypedValuationAgent
from app.agents.valuation_grounding import (
    all_scenario_values_grounded,
    unsupported_numerical_claim_count,
)
from app.clients import RouterClient
from app.config import get_settings
from app.contracts import NextActionDecision, ValuationReport, ValuationSynthesis
from app.evaluation.four_way import DirectStructuredClient, FrozenValuationClient, WorkerBundle
from app.llm import build_nooa_controller_llm

CASE_PATH = Path("/sandbox/fixtures/eval/phase1b_aapl.json")


def _capture_raw_enabled() -> bool:
    return os.getenv("EVAL_CAPTURE_RAW", "").lower() in {"1", "true", "yes"}


class RawNooaTrace:
    """Opt-in capture of synthetic evaluation prompt/output events only."""

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


def _direct_messages(stage: str, context: str) -> list[dict[str, str]]:
    if stage == "decision":
        system = (
            "Return only a JSON object matching NextActionDecision. Choose RUN_SCENARIO, "
            "DELEGATE_REASON, or FINALIZE. Java observations are authoritative. Do not invent "
            "numbers, tools, or Python. Prefer FINALIZE when evidence is sufficient."
        )
    else:
        system = (
            "Return only a JSON object matching ValuationSynthesis. Do not use digits or make "
            "numerical claims. Copy selected_model exactly as valuation_basis. Use only supplied "
            "Java warnings and observations."
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": context}]


async def _direct_condition(name: str, model: str) -> dict[str, Any]:
    settings = get_settings()
    data, question = FrozenValuationClient.from_path(CASE_PATH)
    agent = ConstrainedTypedValuationAgent(data, llm=build_nooa_controller_llm(settings))
    client = DirectStructuredClient(
        base_url=str(settings.ministral_controller_base_url),
        model=model,
        timeout_seconds=settings.http_timeout_seconds,
    )
    started = perf_counter()
    scenario = None
    decisions: list[dict[str, Any]] = []
    try:
        compact = await agent.get_compact_valuation("AAPL")
        for _ in range(3):
            context = agent.build_decision_context(
                question, compact, scenario, None, "EVIDENCE_COLLECTED"
            )
            decision = await client.generate(
                "decision", _direct_messages("decision", context), NextActionDecision
            )
            decisions.append(decision.model_dump())
            if decision.action == "RUN_SCENARIO":
                scenario = await agent.run_compact_valuation_scenario("AAPL", "BULL")
                continue
            if decision.action == "FINALIZE":
                synthesis_context = agent.build_synthesis_context(question, compact, scenario, None)
                synthesis = await client.generate(
                    "synthesis",
                    _direct_messages("synthesis", synthesis_context),
                    ValuationSynthesis,
                )
                report = agent.materialize_evaluation_report(compact, scenario, synthesis)
                agent.validate_final_report(report)
                return _success_record(name, started, report, decisions, client.calls, agent, [])
            raise RuntimeError("direct baseline selected unavailable DELEGATE_REASON")
        raise RuntimeError("bounded_loop_exhaustion")
    except Exception as exc:
        return _failure_record(
            name, started, decisions, client.calls, agent, type(exc).__name__, str(exc)
        )
    finally:
        await client.aclose()


async def _nooa_condition(name: str, *, with_workers: bool) -> dict[str, Any]:
    settings = get_settings()
    data, question = FrozenValuationClient.from_path(CASE_PATH)
    router = RouterClient(settings)
    agent = ConstrainedTypedValuationAgent(
        data,
        reasoning_client=None,
        llm=build_nooa_controller_llm(settings),
    )
    recorder = RawNooaTrace()
    if _capture_raw_enabled():
        recorder.attach(agent.event_manager)
    bundle = WorkerBundle(router) if with_workers else None
    started = perf_counter()
    try:
        report = await agent.investigate_constrained(
            question=question, symbol="AAPL", evaluation_worker_bundle=bundle
        )
        return _success_record(
            name,
            started,
            report,
            [item["decision"] for item in agent.phase1b_trace.trajectory if item.get("decision")],
            [],
            agent,
            recorder.events,
            worker_calls=bundle.calls if bundle else [],
        )
    except Exception as exc:
        return _failure_record(
            name,
            started,
            [
                item["decision"]
                for item in agent.phase1b_trace.trajectory
                if item.get("decision") is not None
            ],
            [],
            agent,
            type(exc).__name__,
            str(exc),
            raw_trace=recorder.events,
            worker_calls=bundle.calls if bundle else [],
        )
    finally:
        await router.aclose()


def _success_record(
    name: str,
    started: float,
    report: ValuationReport,
    decisions: list[dict[str, Any]],
    calls: list[Any],
    agent: ConstrainedTypedValuationAgent,
    raw_trace: list[dict[str, str]],
    *,
    worker_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "condition": name,
        "success": True,
        "total_latency_ms": (perf_counter() - started) * 1000,
        "decisions": decisions,
        "model_calls": [item.__dict__ for item in calls],
        "worker_calls": worker_calls or [],
        "nooa_raw_trace": raw_trace,
        "typed_final_success": True,
        "grounding_success": all_scenario_values_grounded(report),
        "unsupported_numerical_claim_count": unsupported_numerical_claim_count(report),
        "scenario_calls": agent.scenario_call_count,
        "dispatcher_failures": agent.phase1b_trace.dispatcher_failures,
        "bounded_loop_status": agent.phase1b_trace.failure_classification or "completed",
        "metrics": _trace_metrics(agent),
        "report": report.model_dump(mode="json"),
    }


def _failure_record(
    name: str,
    started: float,
    decisions: list[dict[str, Any]],
    calls: list[Any],
    agent: ConstrainedTypedValuationAgent,
    error_type: str,
    error: str,
    *,
    raw_trace: list[dict[str, str]] | None = None,
    worker_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "condition": name,
        "success": False,
        "total_latency_ms": (perf_counter() - started) * 1000,
        "decisions": decisions,
        "model_calls": [item.__dict__ for item in calls],
        "worker_calls": worker_calls or [],
        "nooa_raw_trace": raw_trace or [],
        "error_type": error_type,
        "error": error[:1000],
        "typed_final_success": False,
        "grounding_success": False,
        "unsupported_numerical_claim_count": None,
        "scenario_calls": agent.scenario_call_count,
        "dispatcher_failures": agent.phase1b_trace.dispatcher_failures,
        "bounded_loop_status": agent.phase1b_trace.failure_classification or "failed",
        "metrics": _trace_metrics(agent),
    }


def _trace_metrics(agent: ConstrainedTypedValuationAgent) -> dict[str, Any]:
    trace = agent.phase1b_trace
    return {
        "typed_decisions_total": trace.typed_decisions_total,
        "typed_decisions_valid": trace.typed_decisions_valid,
        "typed_decision_failures": trace.typed_decision_failures,
        "dispatcher_actions_total": trace.dispatcher_actions_total,
        "dispatcher_failures": trace.dispatcher_failures,
        "r1_calls": trace.r1_calls,
        "scenario_calls": trace.scenario_calls,
        "recovery_decisions": trace.recovery_decisions,
        "finalization_attempts": trace.finalization_attempts,
        "typed_final_success": trace.typed_final_success,
        "grounding_success": trace.grounding_success,
    }


async def main() -> None:
    conditions = {
        "direct_gemma": lambda: _direct_condition(
            "direct_gemma", os.getenv("EVAL_GEMMA_MODEL", "gemma4:e4b")
        ),
        "direct_ministral": lambda: _direct_condition(
            "direct_ministral", os.getenv("EVAL_MINISTRAL_MODEL", "ministral-3:8b")
        ),
        "nooa_ministral_no_router": lambda: _nooa_condition(
            "nooa_ministral_no_router", with_workers=False
        ),
        "nooa_ministral_router_three_workers": lambda: _nooa_condition(
            "nooa_ministral_router_three_workers", with_workers=True
        ),
    }
    selected = os.getenv("EVAL_CONDITION")
    if selected and selected not in conditions:
        raise ValueError(f"unknown EVAL_CONDITION: {selected}")
    names = [selected] if selected else list(conditions)
    results = [await conditions[name]() for name in names]
    artifact = {
        "event": "phase1b_four_way_evaluation",
        "case": "synthetic-aapl-phase1b-v1",
        "raw_trace_opt_in": _capture_raw_enabled(),
        "results": results,
    }
    rendered = json.dumps(artifact, ensure_ascii=False, default=str)
    output_path = os.getenv("EVAL_OUTPUT_PATH")
    if output_path:
        Path(output_path).write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    asyncio.run(main())
