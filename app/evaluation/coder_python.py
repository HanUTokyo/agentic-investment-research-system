"""Evaluation-only harness for direct local-coder Python generation.

This module is deliberately outside application orchestration. It evaluates raw
code text returned through the existing Router ``code`` route, then runs the
result only inside a resource-limited Docker container with no network.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.clients import RouterClient

_CODE_FENCE = re.compile(r"```(?:python)?\s*\n(?P<code>.*?)\n```", re.DOTALL | re.IGNORECASE)
_FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.With, ast.AsyncWith, ast.Global, ast.Nonlocal)


@dataclass(frozen=True)
class CoderPythonCase:
    case_id: str
    prompt: str
    function_name: str
    test_source: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CoderPythonCase:
        required = ("case_id", "prompt", "function_name", "test_source")
        if any(not isinstance(value.get(field), str) or not value[field] for field in required):
            raise ValueError("coder case has invalid required fields")
        return cls(**{field: value[field] for field in required})


@dataclass(frozen=True)
class CoderCompletion:
    content: str
    model: str | None
    route: str
    latency_ms: float


class CoderCompletionClient(Protocol):
    async def complete_code(self, messages: list[dict[str, str]]) -> CoderCompletion: ...


class RouterCoderCompletionClient:
    """Adapter for the integrated Router condition."""

    def __init__(self, router: RouterClient) -> None:
        self._router = router

    async def complete_code(self, messages: list[dict[str, str]]) -> CoderCompletion:
        completion = await self._router.complete(
            messages, temperature=0, max_tokens=512, route_hint="code"
        )
        return CoderCompletion(
            content=completion.content,
            model=completion.model,
            route=completion.route or "code",
            latency_ms=completion.latency_ms,
        )


class DirectOllamaCoderCompletionClient:
    """Capability-only client: isolates a named local Ollama coder from Router behavior."""

    def __init__(self, base_url: str, model: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=360.0)
        self._model = model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete_code(self, messages: list[dict[str, str]]) -> CoderCompletion:
        started = perf_counter()
        response = await self._client.post(
            "/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        response.raise_for_status()
        try:
            content = response.json()["message"]["content"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Ollama returned no text completion") from exc
        if not isinstance(content, str):
            raise ValueError("Ollama returned non-text completion")
        return CoderCompletion(
            content=content,
            model=self._model,
            route="direct_ollama_capability_only",
            latency_ms=(perf_counter() - started) * 1_000,
        )


def load_cases(path: Path) -> tuple[CoderPythonCase, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("coder dataset must be a JSON list")
    cases = tuple(CoderPythonCase.from_dict(item) for item in raw if isinstance(item, dict))
    if len(cases) != len(raw) or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("coder dataset cases must be uniquely valid")
    return cases


def extract_python(raw: str) -> str:
    """Extract exactly one Python fence; prose around it is not programming failure."""
    text = raw.strip()
    fences = list(_CODE_FENCE.finditer(text))
    if len(fences) == 1:
        return fences[0].group("code").strip()
    if fences:
        raise ValueError("generated response contains multiple code blocks")
    return text


def validate_python(code: str, function_name: str) -> None:
    """Apply a narrow static safety/contract gate before sandbox execution."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError("generated code is not valid Python") from exc
    if any(isinstance(node, _FORBIDDEN_NODES) for node in ast.walk(tree)):
        raise ValueError("generated code contains a prohibited construct")
    if any(isinstance(node, ast.Name) and node.id.startswith("__") for node in ast.walk(tree)):
        raise ValueError("generated code accesses dunder names")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != function_name:
        raise ValueError("generated code must define exactly the requested function")


def execute_in_sandbox(
    code: str, test_source: str, *, image: str = "python:3.12-alpine"
) -> dict[str, Any]:
    """Execute a generated candidate only in a no-network read-only Docker sandbox."""
    with tempfile.TemporaryDirectory(prefix="coder-python-eval-") as directory:
        work = Path(directory)
        (work / "solution.py").write_text(code + "\n", encoding="utf-8")
        (work / "test_solution.py").write_text(test_source, encoding="utf-8")
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",  # noqa: S108 - Docker tmpfs mount, not a host path.
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            "128m",
            "--cpus",
            "0.25",
            "--user",
            "10001:10001",
            "--volume",
            f"{work}:/work:ro",
            "--workdir",
            "/work",
            image,
            "python",
            "test_solution.py",
        ]
        started = perf_counter()
        try:
            completed = subprocess.run(  # noqa: S603 - fixed Docker sandbox invocation for untrusted candidates.
                command, capture_output=True, text=True, timeout=20, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "executed": False,
                "passed": False,
                "error_type": type(exc).__name__,
                "stderr": str(exc)[:1_000],
                "latency_ms": (perf_counter() - started) * 1_000,
            }
    return {
        "executed": True,
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-1_000:],
        "stderr": completed.stderr[-1_000:],
        "latency_ms": (perf_counter() - started) * 1_000,
    }


async def run_case(client: CoderCompletionClient, case: CoderPythonCase) -> dict[str, Any]:
    """Generate one candidate through the selected eval condition and evaluate it."""
    completion = await client.complete_code(
        [
            {
                "role": "system",
                "content": "Return Python source only. Do not use Markdown, imports, files, shell, network, or prose.",
            },
            {"role": "user", "content": case.prompt},
        ]
    )
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "model": completion.model,
        "route": completion.route,
        "generation_latency_ms": completion.latency_ms,
        "raw_response": completion.content,
    }
    try:
        code = extract_python(completion.content)
        validate_python(code, case.function_name)
    except ValueError as exc:
        record.update({"static_valid": False, "passed": False, "error": str(exc)})
        return record
    record.update(
        {
            "static_valid": True,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
            "sandbox": execute_in_sandbox(code, case.test_source),
        }
    )
    record["passed"] = bool(record["sandbox"]["passed"])
    return record
