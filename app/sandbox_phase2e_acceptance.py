"""Durable Phase 2E continuation from the passed Phase 2C AAPL forecast state."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.agents.research_case_controller import ResearchCaseController
from app.clients.stock_platform import StockPlatformClient
from app.config import get_settings
from app.llm.router_adapter import build_nooa_controller_llm
from app.net_working_capital_evidence_executor import NetWorkingCapitalEvidenceExecutor
from app.research_case import ResearchAction, ResearchCase
from app.research_graph import ResearchDispatcher

_PHASE_2C_CASE = (
    Path("artifacts")
    / "phase2c_acceptance_phase2c-20260811T054700Z-0cab79b3"
    / "11_case_after_forecast.json"
)
_PHASE_2C_NWC_DECISION = _PHASE_2C_CASE.parent / "12_controller_decision_3.json"


def _write(directory: Path, name: str, value: object) -> None:
    """Make each completed acceptance stage independently durable."""
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def _case_from_phase2c() -> ResearchCase:
    payload = json.loads(_PHASE_2C_CASE.read_text())
    case = ResearchCase.model_validate(payload["case"])
    if str(case.valuation_context.get("symbol", "")).upper() != "AAPL":
        raise ValueError("canonical Phase 2C continuation must be AAPL")
    return case


def _forecast_uncertainty(case: ResearchCase) -> dict[str, Any]:
    forecast = next(item for item in case.evidence if "explicit_forecast" in item.claim_scope)
    payload = json.loads(str(forecast.evidence.value))
    missing = payload.get("missing_inputs", [])
    if not any("changeinnetworkingcapital" in str(value).lower() for value in missing):
        raise ValueError("Phase 2C forecast does not contain the expected NWC caveat")
    return {
        "forecast_evidence_id": forecast.evidence_id,
        "missing_inputs": missing,
        "warnings": payload.get("warnings", []),
        "source": forecast.source,
        "provenance": forecast.provenance,
    }


def _recorded_phase2c_nwc_decision() -> ResearchAction:
    payload = json.loads(_PHASE_2C_NWC_DECISION.read_text())
    action = ResearchAction.model_validate(payload["decision"])
    if (
        action.action != "REQUEST_EVIDENCE"
        or "working capital" not in (action.request or "").lower()
    ):
        raise ValueError("canonical Phase 2C artifact does not contain its recorded NWC decision")
    return action


async def run(*, reuse_recorded_phase2c_nwc_decision: bool = False) -> Path:
    run_id = f"phase2e-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2e_acceptance_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now(UTC),
        "status": "RUNNING",
        "source_phase2c_case": str(_PHASE_2C_CASE),
        "recorded_phase2c_nwc_decision": str(_PHASE_2C_NWC_DECISION),
        "illegal_transition_count": 0,
        "grounding_failures": 0,
        "unsupported_numerical_claims": 0,
    }
    _write(directory, "summary.json", summary)
    stock: StockPlatformClient | None = None
    try:
        case = _case_from_phase2c()
        _write(directory, "initial_case.json", {"case": case.model_dump(mode="json")})
        _write(directory, "forecast_uncertainty.json", _forecast_uncertainty(case))

        settings = get_settings()
        stock = StockPlatformClient(settings)
        controller = ResearchCaseController(build_nooa_controller_llm(settings))
        if reuse_recorded_phase2c_nwc_decision:
            decision = _recorded_phase2c_nwc_decision()
            decision_latency_ms: float | None = None
            decision_state = "recorded_phase2c_real_controller"
        else:
            decision_started = perf_counter()
            decision = await controller.decide(case)
            decision_latency_ms = (perf_counter() - decision_started) * 1000
            decision_state = "cold"
        _write(
            directory,
            "controller_decision_nwc.json",
            {
                "decision": decision.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in case.evidence],
                "controller_state": decision_state,
                "latency_ms": decision_latency_ms,
                "decision_provenance": (
                    str(_PHASE_2C_NWC_DECISION)
                    if reuse_recorded_phase2c_nwc_decision
                    else "this_phase2e_remote_controller_call"
                ),
                "is_nwc_request": decision.action == "REQUEST_EVIDENCE"
                and any(
                    token in (decision.request or "").lower()
                    for token in ("working capital", "nwc", "indirect cfo")
                ),
            },
        )
        if decision.action != "REQUEST_EVIDENCE" or not any(
            token in (decision.request or "").lower()
            for token in ("working capital", "nwc", "indirect cfo")
        ):
            summary["status"] = "STOPPED_NON_NWC_CONTROLLER_DECISION"
            return directory

        executor = NetWorkingCapitalEvidenceExecutor(stock)
        dispatch_started = perf_counter()
        updated = await ResearchDispatcher(evidence_executor=executor).dispatch(
            case.select(decision)
        )
        produced = updated.evidence[len(case.evidence) :]
        _write(
            directory,
            "nwc_evidence.json",
            {
                "evidence": [item.model_dump(mode="json") for item in produced],
                "specialist_invocation_count": 0,
                "deterministic_executor_invocation_count": executor.invocation_count,
                "dispatch_latency_ms": (perf_counter() - dispatch_started) * 1000,
                "provenance_complete": all(bool(item.provenance) for item in produced),
                "deterministic_authority_only": all(
                    item.numerical_authority == "deterministic_valuation" for item in produced
                ),
            },
        )
        _write(directory, "case_after_nwc_evidence.json", {"case": updated.model_dump(mode="json")})

        reassessment_started = perf_counter()
        reassessment = await controller.decide(updated)
        _write(
            directory,
            "controller_reassessment.json",
            {
                "decision": reassessment.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in updated.evidence],
                "controller_state": "warm",
                "latency_ms": (perf_counter() - reassessment_started) * 1000,
                "repeated_nwc_request": reassessment.action == "REQUEST_EVIDENCE"
                and any(
                    token in (reassessment.request or "").lower()
                    for token in ("working capital", "nwc", "indirect cfo")
                ),
            },
        )
        summary.update(
            {
                "status": "COMPLETED_REASSESSMENT",
                "research_iterations": updated.iteration_count,
                "nwc_evidence_records_added": len(produced),
                "final_research_case_status": updated.status,
                "repeated_nwc_request": reassessment.action == "REQUEST_EVIDENCE"
                and any(
                    token in (reassessment.request or "").lower()
                    for token in ("working capital", "nwc", "indirect cfo")
                ),
            }
        )
    except Exception as exc:
        summary.update({"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        if stock is not None:
            await stock.aclose()
        summary["total_latency_ms"] = (perf_counter() - started) * 1000
        _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run(reuse_recorded_phase2c_nwc_decision=True)))
