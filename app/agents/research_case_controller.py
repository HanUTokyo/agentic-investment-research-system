"""Bounded Phase 2 Controller that chooses a ResearchAction from current case state."""

from __future__ import annotations

import json
from typing import Any

from nooa import Agent
from nooa.config import PredictConfig
from nooa.decorators import strategy
from nooa.strategies import PredictStrategy

from app.research_case import ResearchAction, ResearchCase

_PREDICT = PredictStrategy(
    config=PredictConfig(max_retries=1, max_tokens=512, temperature=0, output_serialization="event")
)


class ResearchCaseController(Agent):
    """Semantic planner only; it has no HTTP, state-write, or scenario capability."""

    def __init__(self, llm: Any) -> None:
        super().__init__(llm=llm)

    @strategy(_PREDICT)
    async def _decide(self, context: str) -> ResearchAction:
        """Choose exactly one typed semantic ResearchAction.

        If market information is absent and the question needs a current market
        observation, choose REQUEST_EVIDENCE and state the bounded information
        need in request. If external business evidence makes an operating
        forecast analysis materially useful, you may choose
        REQUEST_VALUATION_ANALYSIS only with valuation_analysis:
        EXPLICIT_FORECAST, DEFAULT_TEMPLATE_PREVIEW, the case symbol, a
        qualitative rationale, and one or more existing external evidence IDs.
        This capability asks Java to use its own template for FCFF/FCFE and
        sensitivity analysis. DEFAULT_TEMPLATE_PREVIEW does not incorporate
        external evidence into assumptions or modify any Java input; it produces
        a separate Java-template analysis for reassessment. It cannot accept
        archetypes, numbers, assumptions, URLs, HTTP instructions, or code.
        It consumes only Java's template/default inputs. New historical or external
        evidence does not change that preview unless a separately legal
        assumption-application capability explicitly exists. Do not request the
        same default preview again when an equivalent one is already present: it
        produces no new research information and deterministic runtime will reject
        it as DUPLICATE_NOOP_ACTION. This does not imply FINALIZE; choose another
        legal action only when it addresses a specific remaining uncertainty.
        Evidence availability is deterministic state. For a requested SEC revenue
        period, use evidence_target with its symbol, fiscal_year, and fiscal_period.
        If availability says that period is NOT_YET_AVAILABLE, it cannot yield new
        evidence now. After the runtime records that outcome, decide whether to
        FINALIZE while citing any existing tracked uncertainty IDs that remain, or
        choose another legal action with genuine information gain. Runtime never
        chooses the closure decision.
        Do not choose it merely because external evidence exists; reassess
        whether it is semantically useful.
        If structured first-party revenue guidance is present, you may select
        EVIDENCE_GROUNDED_OVERRIDE with YEAR_1_REVENUE_GUIDANCE and its existing
        evidence ID when it is semantically warranted. You choose only whether
        to apply that evidence and why. Never supply a guidance value, growth
        rate, or any other numerical assumption; deterministic software owns
        period/unit validation and numerical conversion.
        Do not claim external evidence changes Java valuation authority.

        {context}
        """
        ...

    async def decide(self, case: ResearchCase) -> ResearchAction:
        context = {
            "query": case.query,
            "objective": case.objective,
            "valuation_context": case.valuation_context,
            "iteration": case.iteration_count,
            "legal_valuation_capabilities": {
                "EXPLICIT_FORECAST": (
                    "Java default-template operating forecast with FCFF, FCFE, and sensitivity; "
                    "requires existing external evidence IDs and provides no model-supplied assumptions."
                ),
                "YEAR_1_REVENUE_GUIDANCE": (
                    "Only legal with EVIDENCE_GROUNDED_OVERRIDE. Controller supplies an external "
                    "evidence ID and rationale only; deterministic code validates fiscal alignment "
                    "and performs every numerical conversion."
                ),
            },
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "source": item.source,
                    "source_type": item.source_type,
                    "claim_scope": item.claim_scope,
                    "claim": item.evidence.claim,
                    "value": self._evidence_for_controller(item),
                    "provenance": item.provenance,
                    "revenue_guidance": (
                        item.revenue_guidance.model_dump(mode="json")
                        if item.revenue_guidance is not None
                        else None
                    ),
                }
                for item in case.evidence
            ],
            "evidence_availability": [
                item.model_dump(mode="json") for item in case.evidence_availability
            ],
            "evidence_request_outcomes": [
                item.model_dump(mode="json") for item in case.evidence_request_outcomes
            ],
            "tracked_uncertainties": [
                item.model_dump(mode="json") for item in case.tracked_uncertainties
            ],
        }
        return await self._decide(json.dumps(context, sort_keys=True))

    @staticmethod
    def _evidence_for_controller(item: Any) -> Any:
        """Expose forecast meaning, not its full Java transport payload, to the LLM."""
        if "explicit_forecast" not in item.claim_scope:
            return str(item.evidence.value)
        try:
            forecast = json.loads(str(item.evidence.value))
            scenarios = forecast["scenarios"]
            return {
                "capability": forecast["capability"],
                "analysis_mode": forecast["analysis_mode"],
                "archetype": forecast["archetype"],
                "readiness": forecast["readiness"],
                "missing_inputs": forecast["missing_inputs"],
                "scenarios": {
                    label: {
                        "fcff_equity_value": result["fcff"]["equityValue"],
                        "fcfe_equity_value": result["fcfe"]["equityValue"],
                        "fcff_reverse_dcf_status": result["fcff_reverse_dcf"]["status"],
                        "fcfe_reverse_dcf_status": result["fcfe_reverse_dcf"]["status"],
                    }
                    for label, result in scenarios.items()
                },
            }
        except (KeyError, TypeError, ValueError):
            # A malformed deterministic payload remains visible and is rejected by its executor;
            # the Controller must not manufacture a substitute interpretation.
            return {"forecast_evidence": "malformed deterministic forecast payload"}
