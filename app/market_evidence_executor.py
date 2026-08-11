"""Deterministic conversion from MarketInformationAgent output into ResearchEvidence."""

from __future__ import annotations

from app.agents.market_information_agent import MarketInformationAgent, MarketInformationRequest
from app.contracts import Evidence
from app.research_case import (
    IllegalResearchTransition,
    ResearchAction,
    ResearchCase,
    ResearchEvidence,
)


class MarketInformationEvidenceExecutor:
    def __init__(self, agent: MarketInformationAgent) -> None:
        self._agent = agent
        self.invocation_count = 0

    async def __call__(self, case: ResearchCase, action: ResearchAction) -> tuple[ResearchEvidence, ...]:
        if action.action != "REQUEST_EVIDENCE":
            raise IllegalResearchTransition("market executor accepts REQUEST_EVIDENCE only")
        if any("market_information" in item.claim_scope for item in case.evidence):
            raise IllegalResearchTransition("identical market information request is already satisfied")
        symbol = str(case.valuation_context.get("symbol", "")).upper()
        if not symbol:
            raise IllegalResearchTransition("market information request requires valuation_context.symbol")
        self.invocation_count += 1
        result = await self._agent.collect(
            MarketInformationRequest(
                symbol=symbol,
                question=case.query,
                information_need=action.request or "",
                relevant_context={"objective": case.objective, "hypothesis": case.current_hypothesis or ""},
            )
        )
        if not result.facts:
            raise IllegalResearchTransition("market specialist returned no factual evidence")
        return tuple(
            ResearchEvidence(
                evidence=Evidence(claim=fact.claim, source_path=f"external.yahoo.{fact.source_path}", value=fact.value),
                source=result.source,
                source_type="external",
                retrieved_at=fact.retrieved_at,
                claim_scope=("market_information",),
                provenance={"url": fact.source_url, "source_path": fact.source_path},
                numerical_authority="external_source",
            )
            for fact in result.facts
        )
