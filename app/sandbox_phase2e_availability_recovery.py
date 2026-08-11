"""Final Phase 2E recovery: availability outcome, then one Controller reassessment."""

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
from app.evidence_availability_executor import FiscalRevenueAvailabilityExecutor
from app.llm.router_adapter import build_nooa_controller_llm
from app.research_case import ResearchCase, ResearchUncertainty
from app.research_graph import ResearchDispatcher

_SOURCE_CASE = (
    Path("artifacts")
    / "phase2e_acceptance_phase2e-20260811T072324Z-00b386a8"
    / "case_after_nwc_evidence.json"
)


def _write(directory: Path, name: str, value: object) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def _nwc_uncertainty(case: ResearchCase) -> ResearchUncertainty:
    forecast = next(item for item in case.evidence if "explicit_forecast" in item.claim_scope)
    return ResearchUncertainty(
        uncertainty_id="explicit-forecast-nwc-caveat",
        description=(
            "The Java explicit forecast retains changeInNetWorkingCapital as an explicit "
            "assumption until the detailed indirect-CFO bridge is complete."
        ),
        source_evidence_id=forecast.evidence_id,
    )


async def run() -> Path:
    run_id = f"phase2e-availability-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2e_availability_recovery_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    summary: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now(UTC),
        "status": "RUNNING",
    }
    _write(directory, "summary.json", summary)
    stock: StockPlatformClient | None = None
    try:
        source = json.loads(_SOURCE_CASE.read_text())
        prior = ResearchCase.model_validate(source["case"])
        settings = get_settings()
        stock = StockPlatformClient(settings)
        history = await stock.get_financial_history("AAPL")
        availability = FiscalRevenueAvailabilityExecutor.availability_from_history("AAPL", history)
        case = prior.model_copy(
            update={
                "evidence_availability": (availability,),
                "tracked_uncertainties": (_nwc_uncertainty(prior),),
                # Phase 2E needs one action to request availability and one to close.
                "max_iterations": 5,
            }
        )
        _write(directory, "initial_case.json", {"case": case.model_dump(mode="json")})
        _write(
            directory,
            "evidence_availability.json",
            {"availability": availability.model_dump(mode="json")},
        )

        controller = ResearchCaseController(build_nooa_controller_llm(settings))
        first_started = perf_counter()
        first = await controller.decide(case)
        _write(
            directory,
            "controller_decision_availability.json",
            {
                "decision": first.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in case.evidence],
                "visible_availability_ids": [
                    item.availability_id for item in case.evidence_availability
                ],
                "tracked_uncertainty_ids": [
                    item.uncertainty_id for item in case.tracked_uncertainties
                ],
                "latency_ms": (perf_counter() - first_started) * 1000,
            },
        )
        if first.action == "FINALIZE" and first.unresolved_uncertainty_ids:
            final = await ResearchDispatcher().dispatch(case.select(first))
            _write(directory, "final_case.json", {"case": final.model_dump(mode="json")})
            summary.update({"status": "CLOSED_WITH_LIMITATIONS", "final_status": final.status})
            return directory
        if first.action != "REQUEST_EVIDENCE" or first.evidence_target is None:
            summary.update({"status": "STOPPED_NO_TYPED_AVAILABILITY_REQUEST"})
            return directory

        availability_executor = FiscalRevenueAvailabilityExecutor()
        dispatch_started = perf_counter()
        after_outcome = await ResearchDispatcher(evidence_executor=availability_executor).dispatch(
            case.select(first)
        )
        outcome = after_outcome.evidence_request_outcomes[-1]
        _write(
            directory,
            "evidence_request_outcome.json",
            {
                "outcome": outcome.model_dump(mode="json"),
                "executor_invocation_count": availability_executor.invocation_count,
                "dispatch_latency_ms": (perf_counter() - dispatch_started) * 1000,
            },
        )
        _write(
            directory,
            "case_after_availability_outcome.json",
            {"case": after_outcome.model_dump(mode="json")},
        )

        second_started = perf_counter()
        second = await controller.decide(after_outcome)
        _write(
            directory,
            "controller_reassessment.json",
            {
                "decision": second.model_dump(mode="json"),
                "visible_evidence_ids": [item.evidence_id for item in after_outcome.evidence],
                "visible_outcome_ids": [
                    item.outcome_id for item in after_outcome.evidence_request_outcomes
                ],
                "tracked_uncertainty_ids": [
                    item.uncertainty_id for item in after_outcome.tracked_uncertainties
                ],
                "latency_ms": (perf_counter() - second_started) * 1000,
            },
        )
        if second.action == "FINALIZE" and second.unresolved_uncertainty_ids:
            final = await ResearchDispatcher().dispatch(after_outcome.select(second))
            _write(directory, "final_case.json", {"case": final.model_dump(mode="json")})
            summary.update({"status": "CLOSED_WITH_LIMITATIONS", "final_status": final.status})
        else:
            summary.update(
                {"status": "REASSESSMENT_DID_NOT_CLOSE", "reassessment_action": second.action}
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
    print(asyncio.run(run()))
