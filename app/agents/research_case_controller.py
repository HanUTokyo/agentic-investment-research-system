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
        need in request. If external market evidence is present, reassess based
        on it; do not claim it changes Java valuation authority. Never emit URLs,
        HTTP instructions, code, or unsupported numerical claims.

        {context}
        """
        ...

    async def decide(self, case: ResearchCase) -> ResearchAction:
        context = {
            "query": case.query,
            "objective": case.objective,
            "valuation_context": case.valuation_context,
            "iteration": case.iteration_count,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "source": item.source,
                    "source_type": item.source_type,
                    "claim_scope": item.claim_scope,
                    "claim": item.evidence.claim,
                    "value": str(item.evidence.value),
                    "provenance": item.provenance,
                }
                for item in case.evidence
            ],
        }
        return await self._decide(json.dumps(context, sort_keys=True))
