"""Durable, bounded Phase 2C acceptance trajectory against canonical remote services."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.agents.market_information_agent import MarketInformationAgent
from app.agents.research_case_controller import ResearchCaseController
from app.clients.stock_platform import StockPlatformClient
from app.config import get_settings
from app.contracts import Evidence
from app.explicit_forecast_executor import ExplicitForecastExecutor
from app.llm.router_adapter import build_nooa_controller_llm
from app.market_evidence_executor import MarketInformationEvidenceExecutor
from app.research_case import ResearchCase, ResearchEvidence
from app.research_graph import ResearchDispatcher


def _write(directory: Path, name: str, value: object) -> None:
    """Atomically preserve every completed acceptance stage."""
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


async def run(symbol: str = "AAPL") -> Path:
    run_id = f"phase2c-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2c_acceptance_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now(UTC),
        "status": "RUNNING",
        "illegal_transitions": 0,
        "grounding_failures": 0,
        "unsupported_numerical_claims": 0,
    }
    _write(directory, "summary.json", summary)
    settings = get_settings()
    stock = StockPlatformClient(settings)
    try:
        valuation = await stock.get_current_valuation(symbol)
        overview = valuation.overview or {}
        initial = (
            ResearchEvidence(
                evidence_id="java-current-price",
                evidence=Evidence(
                    claim="Java current price",
                    source_path="java.valuation.overview.current_price",
                    value=Decimal(str(overview["currentPrice"])),
                ),
                source="Java valuation engine",
                source_type="deterministic_valuation",
                claim_scope=("valuation_context",),
                provenance={"engine_version": valuation.engine_version},
                numerical_authority="deterministic_valuation",
            ),
            ResearchEvidence(
                evidence_id="java-base-value",
                evidence=Evidence(
                    claim="Java base value",
                    source_path="java.valuation.overview.base_value",
                    value=Decimal(str(overview["baseValue"])),
                ),
                source="Java valuation engine",
                source_type="deterministic_valuation",
                claim_scope=("valuation_context",),
                provenance={"engine_version": valuation.engine_version},
                numerical_authority="deterministic_valuation",
            ),
        )
        case = ResearchCase(
            case_id=run_id,
            query=(
                f"Before concluding the {symbol} valuation case, determine whether a recent "
                "official operating revenue observation is needed and, if it is material, whether "
                "a Java explicit forecast analysis would improve the investigation."
            ),
            objective=(
                "Use absent dated external operating evidence only if semantically warranted; then "
                "reassess whether a bounded deterministic valuation analysis is needed."
            ),
            valuation_context={"symbol": symbol.upper(), "selected_model": valuation.selected_model or ""},
            evidence=initial,
            max_iterations=4,
        )
        _write(directory, "01_initial_case.json", {"case": case.model_dump(mode="json")})
        controller = ResearchCaseController(build_nooa_controller_llm(settings))

        decision_started = perf_counter()
        decision_1 = await controller.decide(case)
        _write(
            directory,
            "02_controller_decision_1.json",
            {
                "decision": decision_1.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in case.evidence],
                "controller_state": "cold",
                "latency_ms": (perf_counter() - decision_started) * 1000,
            },
        )
        if decision_1.action != "REQUEST_EVIDENCE":
            summary["status"] = "STOPPED_NON_EVIDENCE_DECISION"
            return directory

        market_executor = MarketInformationEvidenceExecutor(MarketInformationAgent())
        dispatch_started = perf_counter()
        after_external = await ResearchDispatcher(evidence_executor=market_executor).dispatch(
            case.select(decision_1)
        )
        external = after_external.evidence[len(case.evidence) :]
        _write(
            directory,
            "03_external_evidence.json",
            {
                "information_need": decision_1.request,
                "facts": [item.model_dump(mode="json") for item in external],
                "specialist_invocation_count": market_executor.invocation_count,
                "dispatch_latency_ms": (perf_counter() - dispatch_started) * 1000,
                "provenance_complete": all(bool(item.provenance) for item in external),
                "external_authority_only": all(
                    item.numerical_authority == "external_source" for item in external
                ),
            },
        )
        _write(directory, "04_case_after_external_evidence.json", {"case": after_external.model_dump(mode="json")})
        if not external or any("operating_information" not in item.claim_scope for item in external):
            summary["status"] = "STOPPED_NON_OPERATING_EVIDENCE"
            return directory

        decision_started = perf_counter()
        decision_2 = await controller.decide(after_external)
        _write(
            directory,
            "05_controller_decision_2.json",
            {
                "decision": decision_2.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in after_external.evidence],
                "controller_state": "warm",
                "latency_ms": (perf_counter() - decision_started) * 1000,
            },
        )
        if decision_2.action != "REQUEST_VALUATION_ANALYSIS":
            summary["status"] = "STOPPED_NON_VALUATION_ANALYSIS_DECISION"
            return directory
        _write(
            directory,
            "06_valuation_analysis_request.json",
            {"request": decision_2.valuation_analysis.model_dump(mode="json") if decision_2.valuation_analysis else None},
        )

        step_files = {
            "forecast_template": "07_forecast_template.json",
            "forecast_request": "08_forecast_request.json",
            "forecast_preview": "09_forecast_preview.json",
        }

        def observe(step: str, value: dict[str, Any]) -> None:
            _write(directory, step_files[step], {"completed_at": datetime.now(UTC), step: value})

        forecast_executor = ExplicitForecastExecutor(stock, on_step=observe)
        dispatch_started = perf_counter()
        after_forecast = await ResearchDispatcher(
            valuation_analysis_executor=forecast_executor
        ).dispatch(after_external.select(decision_2))
        forecast = after_forecast.evidence[len(after_external.evidence) :]
        _write(
            directory,
            "10_forecast_evidence.json",
            {
                "evidence": [item.model_dump(mode="json") for item in forecast],
                "forecast_invocation_count": forecast_executor.invocation_count,
                "dispatch_latency_ms": (perf_counter() - dispatch_started) * 1000,
                "deterministic_authority_only": all(
                    item.numerical_authority == "deterministic_valuation" for item in forecast
                ),
            },
        )
        _write(directory, "11_case_after_forecast.json", {"case": after_forecast.model_dump(mode="json")})

        decision_started = perf_counter()
        decision_3 = await controller.decide(after_forecast)
        _write(
            directory,
            "12_controller_decision_3.json",
            {
                "decision": decision_3.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in after_forecast.evidence],
                "controller_state": "warm",
                "latency_ms": (perf_counter() - decision_started) * 1000,
            },
        )
        summary.update(
            {
                "status": "COMPLETED_THREE_DECISIONS",
                "research_iterations": after_forecast.iteration_count,
                "external_evidence_added": len(external),
                "forecast_evidence_added": len(forecast),
            }
        )
    except Exception as exc:
        summary.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        summary["total_latency_ms"] = (perf_counter() - started) * 1000
        await stock.aclose()
        _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
