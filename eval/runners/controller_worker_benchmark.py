"""Summarize recorded, opt-in controller benchmark trajectories.

This runner consumes sanitized JSONL outcomes. It does not run models itself,
which keeps CI independent of Router, Ollama, Java, and private portfolio data.
"""

import json
from pathlib import Path

from eval.metrics.controller_worker import RunOutcome, summarize


def load_outcomes(path: Path) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    for line in path.read_text().splitlines():
        if line.strip():
            outcomes.append(RunOutcome(**json.loads(line)))
    return outcomes


def benchmark(controller_only: Path, controller_worker: Path) -> dict[str, object]:
    """Compare recorded runs without assuming the worker is beneficial."""
    return {
        "controller_only": summarize(load_outcomes(controller_only)),
        "controller_plus_worker": summarize(load_outcomes(controller_worker)),
    }
