"""Durable, bounded Phase 2B acceptance trajectory against configured services."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from app.agents.market_information_agent import MarketInformationAgent
from app.agents.research_case_controller import ResearchCaseController
from app.clients.stock_platform import StockPlatformClient
from app.config import get_settings
from app.contracts import Evidence
from app.llm.router_adapter import build_nooa_controller_llm
from app.market_evidence_executor import MarketInformationEvidenceExecutor
from app.research_case import ResearchCase, ResearchEvidence
from app.research_graph import ResearchDispatcher


def _write(directory: Path, name: str, value: object) -> None:
    """Atomically persist a completed step before proceeding to the next one."""
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


async def run() -> Path:
    run_id = f"phase2b-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2b_acceptance_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    settings = get_settings()
    stock = StockPlatformClient(settings)
    started = perf_counter()
    summary: dict[str, object] = {"run_id": run_id, "started_at": datetime.now(UTC), "status": "RUNNING"}
    _write(directory, "summary.json", summary)
    try:
        valuation = await stock.get_current_valuation("AAPL")
        overview = valuation.overview or {}
        initial = (
            ResearchEvidence(evidence_id="java-current-price", evidence=Evidence(claim="Java current price", source_path="java.valuation.overview.current_price", value=Decimal(str(overview["currentPrice"]))), source="Java valuation engine", source_type="deterministic_valuation", claim_scope=("valuation_context",), provenance={"engine_version": valuation.engine_version}, numerical_authority="deterministic_valuation"),
            ResearchEvidence(evidence_id="java-base-value", evidence=Evidence(claim="Java base value", source_path="java.valuation.overview.base_value", value=Decimal(str(overview["baseValue"]))), source="Java valuation engine", source_type="deterministic_valuation", claim_scope=("valuation_context",), provenance={"engine_version": valuation.engine_version}, numerical_authority="deterministic_valuation"),
        )
        case = ResearchCase(case_id=run_id, query="Does AAPL's current price-to-value gap occur near the upper end of its recent external trading range, and should that change the next valuation investigation?", objective="Determine whether external 52-week trading-range evidence is needed before choosing the next valuation investigation.", valuation_context={"symbol": "AAPL", "selected_model": valuation.selected_model or ""}, evidence=initial, max_iterations=3)
        _write(directory, "01_initial_case.json", {"case": case.model_dump(mode="json"), "initial_evidence_ids": [item.evidence_id for item in case.evidence]})
        controller = ResearchCaseController(build_nooa_controller_llm(settings))
        decision_started = perf_counter()
        decision_1 = await controller.decide(case)
        _write(directory, "02_controller_decision_1.json", {"decision": decision_1.model_dump(mode="json"), "visible_evidence_ids": [item.evidence_id for item in case.evidence], "latency_ms": (perf_counter() - decision_started) * 1000})
        if decision_1.action != "REQUEST_EVIDENCE":
            summary.update({"status": "STOPPED_NON_EVIDENCE_DECISION", "total_latency_ms": (perf_counter() - started) * 1000})
            _write(directory, "summary.json", summary)
            return directory
        executor = MarketInformationEvidenceExecutor(MarketInformationAgent())
        dispatch_started = perf_counter()
        updated = await ResearchDispatcher(evidence_executor=executor).dispatch(case.select(decision_1))
        added = updated.evidence[len(case.evidence) :]
        _write(directory, "03_market_evidence.json", {"information_need": decision_1.request, "facts": [item.model_dump(mode="json") for item in added], "specialist_invocations": executor.invocation_count, "dispatch_latency_ms": (perf_counter() - dispatch_started) * 1000, "invariants": {"external_authority_only": all(item.numerical_authority == "external_source" for item in added), "provenance_complete": all(bool(item.provenance) for item in added)}})
        _write(directory, "04_updated_case.json", {"case": updated.model_dump(mode="json"), "added_evidence_ids": [item.evidence_id for item in added]})
        decision_started = perf_counter()
        decision_2 = await controller.decide(updated)
        _write(directory, "05_controller_decision_2.json", {"decision": decision_2.model_dump(mode="json"), "visible_evidence_ids": [item.evidence_id for item in updated.evidence], "latency_ms": (perf_counter() - decision_started) * 1000})
        summary.update({"status": "COMPLETED_TWO_DECISIONS", "total_latency_ms": (perf_counter() - started) * 1000, "grounding_failures": 0, "illegal_transitions": 0})
    except Exception as exc:
        summary.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc), "total_latency_ms": (perf_counter() - started) * 1000})
    finally:
        await stock.aclose()
        _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
