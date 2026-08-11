from decimal import Decimal

import httpx
import pytest

from app.agents.market_information_agent import (
    MarketInformationAgent,
    MarketInformationError,
    MarketInformationRequest,
)
from app.market_evidence_executor import MarketInformationEvidenceExecutor
from app.research_case import IllegalResearchTransition, ResearchAction, ResearchCase
from app.research_graph import ResearchDispatcher, build_research_graph


@pytest.mark.asyncio
async def test_market_agent_converts_real_source_shape_to_provenance_complete_evidence() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"chart": {"result": [{"meta": {"fiftyTwoWeekHigh": 222.5, "fiftyTwoWeekLow": 100}}]}}))
    async with httpx.AsyncClient(transport=transport) as client:
        executor = MarketInformationEvidenceExecutor(MarketInformationAgent(client))
        case = ResearchCase(query="What is the current market observation?", objective="Assess valuation", valuation_context={"symbol": "AAPL"})
        action = ResearchAction(action="REQUEST_EVIDENCE", reason="Market data is absent", request="Obtain a current market observation.")
        evidence = await executor(case, action)

    assert executor.invocation_count == 1
    assert evidence[0].source_type == "external"
    assert evidence[0].numerical_authority == "external_source"
    assert evidence[0].provenance["url"].startswith("https://query1.finance.yahoo.com")
    assert [item.evidence.value for item in evidence] == [Decimal("222.5"), Decimal("100")]


@pytest.mark.asyncio
async def test_market_executor_rejects_repeat_and_malformed_source_output() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"chart": {"result": [{}]}}))
    async with httpx.AsyncClient(transport=transport) as client:
        agent = MarketInformationAgent(client)
        with pytest.raises(MarketInformationError, match="52-week range"):
            await agent.collect(MarketInformationRequest(symbol="AAPL", question="q", information_need="need"))

    case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "AAPL"})
    action = ResearchAction(action="REQUEST_EVIDENCE", reason="need", request="market")
    existing = ResearchCase.model_validate({**case.model_dump(), "evidence": [{"evidence": {"claim": "prior", "sourcePath": "external.x"}, "source": "SEC", "source_type": "external", "claim_scope": ["market_information"]}]})
    with pytest.raises(IllegalResearchTransition, match="already satisfied"):
        await MarketInformationEvidenceExecutor(MarketInformationAgent()).__call__(existing, action)


@pytest.mark.asyncio
async def test_market_agent_retrieves_dated_sec_operating_observation_with_provenance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"ticker": "ACME", "cik_str": 1234}})
        if request.url.path.endswith("CIK0000001234.json"):
            return httpx.Response(
                200,
                json={
                    "facts": {
                        "us-gaap": {
                            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                                "units": {
                                    "USD": [
                                        {
                                            "form": "10-Q", "fp": "Q2", "fy": 2026,
                                            "filed": "2026-08-01", "end": "2026-06-30",
                                            "val": 1250000, "accn": "0000001234-26-000001",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        executor = MarketInformationEvidenceExecutor(MarketInformationAgent(client))
        case = ResearchCase(query="q", objective="o", valuation_context={"symbol": "ACME"})
        evidence = await executor(
            case,
            ResearchAction(
                action="REQUEST_EVIDENCE", reason="Need filing evidence",
                request="Obtain an official operating revenue observation.",
            ),
        )

    assert evidence[0].claim_scope == ("operating_information",)
    assert evidence[0].source == "SEC company facts API"
    assert evidence[0].evidence.source_path.startswith("external.sec.")
    assert evidence[0].provenance["form"] == "10-Q"
    assert evidence[0].provenance["filed"] == "2026-08-01"


@pytest.mark.asyncio
async def test_controller_reassesses_the_evidence_added_by_dispatcher() -> None:
    class EvidenceAwareController:
        def __init__(self) -> None:
            self.evidence_seen: list[tuple[str, ...]] = []

        async def decide(self, case: ResearchCase) -> ResearchAction:
            self.evidence_seen.append(tuple(item.evidence_id for item in case.evidence))
            if not case.evidence:
                return ResearchAction(action="REQUEST_EVIDENCE", reason="Market evidence is missing", request="current market observation")
            return ResearchAction(action="DELEGATE_SPECIALIST", reason="Updated evidence requires a fresh semantic decision")

    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"chart": {"result": [{"meta": {"fiftyTwoWeekHigh": 2, "fiftyTwoWeekLow": 1}}]}}))
    async with httpx.AsyncClient(transport=transport) as client:
        controller = EvidenceAwareController()
        graph = build_research_graph(controller, ResearchDispatcher(evidence_executor=MarketInformationEvidenceExecutor(MarketInformationAgent(client))))
        with pytest.raises(IllegalResearchTransition, match="no specialist"):
            await graph.ainvoke({"case": ResearchCase(query="q", objective="o", valuation_context={"symbol": "AAPL"}, max_iterations=2)}, config={"configurable": {"thread_id": "updated-evidence"}})

    assert controller.evidence_seen[0] == ()
    assert len(controller.evidence_seen[1]) == 2
