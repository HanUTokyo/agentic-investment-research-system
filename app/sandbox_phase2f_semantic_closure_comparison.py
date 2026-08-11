"""Phase 2F-B: semantic-only closure comparison over one frozen ResearchCase.

This intentionally bypasses NOOA/Pydantic typed-action serialization.  It is an
evaluation probe only: no dispatcher, executor, tool call, state mutation, JSON
repair, or decision compilation is performed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

from app.research_case import ResearchCase

_SOURCE_CASE = (
    Path("artifacts")
    / "phase2e_availability_recovery_phase2e-availability-20260811T074656Z-7af3e793"
    / "initial_case.json"
)
_MODELS = ("ministral-3:8b", "deepseek-r1:8b")
_RUNS_PER_MODEL = 3
_CHOICES = {
    "FINALIZE",
    "FINALIZE_WITH_LIMITATIONS",
    "REQUEST_EVIDENCE",
    "REQUEST_VALUATION_ANALYSIS",
}
_EXPECTED_UNCERTAINTY = "explicit-forecast-nwc-caveat"


def _write(directory: Path, name: str, value: object) -> None:
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    temporary.write_text(json.dumps(value, default=str, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)


def _case_hash(case: ResearchCase) -> str:
    payload = json.dumps(case.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _prompt(case: ResearchCase) -> str:
    projection = {
        "query": case.query,
        "objective": case.objective,
        "iteration": case.iteration_count,
        "evidence": [
            {
                "id": item.evidence_id,
                "scope": item.claim_scope,
                "claim": item.evidence.claim,
                "source": item.source,
                "authority": item.numerical_authority,
                "provenance": item.provenance,
            }
            for item in case.evidence
        ],
        "evidence_availability": [
            item.model_dump(mode="json") for item in case.evidence_availability
        ],
        "executed_actions": [item.action.model_dump(mode="json") for item in case.executed_actions],
        "tracked_uncertainties": [
            item.model_dump(mode="json") for item in case.tracked_uncertainties
        ],
        "capability_semantics": {
            "DEFAULT_TEMPLATE_PREVIEW": "Uses only Java template defaults. Existing NWC evidence does not change its effective inputs; equivalent repeats are no-op.",
            "availability": "A later SEC reported-revenue period than the latest recorded period is not currently available.",
            "nwc": "No legal capability currently consumes historical NWC observations into a forecast assumption.",
        },
    }
    return """You are evaluating semantic research closure only. Do not propose tools, code, HTTP, numbers, or a JSON object.

Choose exactly one next-step label from:
FINALIZE
FINALIZE_WITH_LIMITATIONS
REQUEST_EVIDENCE
REQUEST_VALUATION_ANALYSIS

If and only if you choose FINALIZE_WITH_LIMITATIONS, identify one existing tracked uncertainty ID.

Return your conclusion at the END of your response in exactly these plain-text lines:
FINAL_DECISION: <one allowed label>
UNRESOLVED_UNCERTAINTY: <existing ID or NONE>

ResearchCase projection:
""" + json.dumps(projection, sort_keys=True)


def _evaluate(raw: str) -> dict[str, Any]:
    """Evaluate explicit final markers; never repair or infer a model decision."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    choices = [
        line.removeprefix("FINAL_DECISION:").strip()
        for line in lines
        if line.startswith("FINAL_DECISION:")
    ]
    uncertainties = [
        line.removeprefix("UNRESOLVED_UNCERTAINTY:").strip()
        for line in lines
        if line.startswith("UNRESOLVED_UNCERTAINTY:")
    ]
    if len(choices) != 1 or choices[0] not in _CHOICES or len(uncertainties) != 1:
        return {"semantic_choice_valid": False, "reason": "missing_or_ambiguous_final_markers"}
    decision, uncertainty = choices[0], uncertainties[0]
    valid_uncertainty = (
        decision == "FINALIZE_WITH_LIMITATIONS" and uncertainty == _EXPECTED_UNCERTAINTY
    ) or (decision != "FINALIZE_WITH_LIMITATIONS" and uncertainty == "NONE")
    return {
        "semantic_choice_valid": valid_uncertainty,
        "decision": decision,
        "unresolved_uncertainty": uncertainty,
        "oracle_match": decision == "FINALIZE_WITH_LIMITATIONS"
        and uncertainty == _EXPECTED_UNCERTAINTY,
    }


async def run() -> Path:
    run_id = f"phase2f-semantic-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    directory = Path("artifacts") / f"phase2f_semantic_closure_comparison_{run_id}"
    directory.mkdir(parents=True, exist_ok=False)
    source = json.loads(_SOURCE_CASE.read_text())
    case = ResearchCase.model_validate(source["case"])
    frozen_hash = _case_hash(case)
    prompt = _prompt(case)
    _write(
        directory,
        "frozen_case.json",
        {"source": str(_SOURCE_CASE), "sha256": frozen_hash, "case": case.model_dump(mode="json")},
    )
    _write(directory, "semantic_prompt.txt.json", {"prompt": prompt})
    summary: dict[str, Any] = {
        "run_id": run_id,
        "status": "RUNNING",
        "frozen_case_sha256": frozen_hash,
        "models": list(_MODELS),
        "runs_per_model": _RUNS_PER_MODEL,
    }
    _write(directory, "summary.json", summary)
    base_url = os.environ["MINISTRAL_CONTROLLER_BASE_URL"].rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=360.0) as client:
        results: dict[str, list[dict[str, Any]]] = {model: [] for model in _MODELS}
        for model in _MODELS:
            for attempt in range(1, _RUNS_PER_MODEL + 1):
                started = perf_counter()
                record: dict[str, Any] = {
                    "model": model,
                    "attempt": attempt,
                    "frozen_case_sha256": frozen_hash,
                    "started_at": datetime.now(UTC),
                }
                try:
                    response = await client.post(
                        "/chat/completions",
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0,
                            "max_tokens": 2_048,
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    raw = str(payload["choices"][0]["message"]["content"])
                    record["raw_response"] = raw
                    record["evaluation"] = _evaluate(raw)
                except Exception as exc:
                    record["evaluation"] = {
                        "semantic_choice_valid": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                record["latency_ms"] = (perf_counter() - started) * 1000
                results[model].append(record)
                _write(directory, f"{model.replace(':', '_')}_attempt_{attempt}.json", record)
                summary["results"] = results
                _write(directory, "summary.json", summary)
    summary["condition_summary"] = {
        model: {
            "valid_semantic_choices": sum(
                item["evaluation"].get("semantic_choice_valid", False) for item in records
            ),
            "oracle_matches": sum(
                item["evaluation"].get("oracle_match", False) for item in records
            ),
            "decisions": [item["evaluation"].get("decision") for item in records],
        }
        for model, records in results.items()
    }
    summary["status"] = "COMPLETED"
    _write(directory, "summary.json", summary)
    return directory


if __name__ == "__main__":
    print(asyncio.run(run()))
