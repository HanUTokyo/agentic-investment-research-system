"""Evaluation-only relaxed NOOA controller without any Router worker capability."""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from nooa.config import PredictConfig
from nooa.decorators import strategy
from nooa.strategies import PredictStrategy

from app.agents.constrained_valuation_agent import ConstrainedTypedValuationAgent
from app.agents.valuation_projection import CompactScenarioObservation
from app.contracts import NoRouterNextActionDecision, ValuationReport

_RELAXED_PREDICT = PredictStrategy(
    config=PredictConfig(
        max_retries=3, max_tokens=1_024, temperature=0, output_serialization="event"
    )
)


class RelaxedNoRouterValuationAgent(ConstrainedTypedValuationAgent):
    """Permit only legal no-router actions and a longer decision explanation.

    This is a separately labelled comparison condition. It does not alter the
    historic strict four-way result or select actions deterministically.
    """

    @strategy(_RELAXED_PREDICT)
    async def decide_next_action_no_router(self, context: str) -> NoRouterNextActionDecision:
        """Choose exactly one action from RUN_SCENARIO or FINALIZE.

        No reasoning worker exists in this condition. Initial Java valuation
        evidence is already available. You cannot call tools, write Python, or
        choose a scenario type. Select RUN_SCENARIO at most once or FINALIZE.
        Do not invent financial numbers or tool names.

        {context}
        """
        ...

    def _no_router_context(
        self, question: str, compact: Any, scenario: CompactScenarioObservation | None
    ) -> str:
        payload = json.loads(
            self.build_decision_context(question, compact, scenario, None, "EVIDENCE_COLLECTED")
        )
        payload["limits"]["r1_calls_remaining"] = 0
        payload["reason_worker"] = {"available": False, "ok": None, "proposal": None}
        payload["available_actions"] = ["RUN_SCENARIO", "FINALIZE"]
        return self._json(payload)

    async def investigate_relaxed_no_router(self, *, question: str, symbol: str) -> ValuationReport:
        trace = self.phase1b_trace
        started = perf_counter()
        compact = await self.get_compact_valuation(symbol)
        trace.record(
            state="EVIDENCE_COLLECTED",
            observation_type="CompactValuationObservation",
            decision_schema=None,
            decision=None,
            dispatcher_action="GET_COMPACT_VALUATION",
            tool_result="success",
            validation_result="valid",
            latency_ms=(perf_counter() - started) * 1000,
        )
        scenario: CompactScenarioObservation | None = None
        for _ in range(2):
            context = self._no_router_context(question, compact, scenario)
            decision_started = perf_counter()
            trace.typed_decisions_total += 1
            try:
                decision = await self.decide_next_action_no_router(context)
            except Exception:
                trace.typed_decision_failures += 1
                trace.failure_classification = "TYPED_DECISION_GENERATION"
                raise
            trace.typed_decisions_valid += 1
            trace.record(
                state="EVIDENCE_COLLECTED" if scenario is None else "SCENARIO_AVAILABLE",
                observation_type="CompactValuationObservation",
                decision_schema="NoRouterNextActionDecision",
                decision=decision.model_dump(),
                dispatcher_action=None,
                tool_result=None,
                validation_result="valid",
                latency_ms=(perf_counter() - decision_started) * 1000,
            )
            if decision.action == "FINALIZE":
                trace.finalization_attempts += 1
                return await self._finalize(question, compact, scenario, None)
            if scenario is not None:
                trace.dispatcher_failures += 1
                trace.failure_classification = "MODEL_SEMANTIC_DECISION"
                raise RuntimeError("RUN_SCENARIO selected after the scenario cap")
            scenario = await self.run_compact_valuation_scenario(symbol, "BULL")
            trace.scenario_calls += 1
            trace.dispatcher_actions_total += 1
            trace.record(
                state="SCENARIO_AVAILABLE",
                observation_type="CompactScenarioObservation",
                decision_schema="NoRouterNextActionDecision",
                decision=decision.model_dump(),
                dispatcher_action="RUN_SCENARIO",
                tool_result="success",
                validation_result="valid",
                latency_ms=None,
            )
        trace.failure_classification = "BOUNDED_LOOP_EXHAUSTION"
        raise RuntimeError("relaxed no-router loop exhausted before FINALIZE")
