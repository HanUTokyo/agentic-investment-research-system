# ADR: Controller–Coder Worker for Phase 1

## Decision

Phase 1 uses a tool-capable controller model (initially Router's configured
Gemma tool model) for the NOOA `CodeActStrategy`. DeepSeek-Coder is available
only as an optional, bounded `CodeWorker` that returns a typed `CodeDraft` via
the Router's explicit `route_hint=code` path.

## Context

NOOA owns the agent protocol: native `execute_python`, observations, iterative
tool use, and the final schema-valid `return_result(ValuationReport)`. The
installed `deepseek-coder:6.7b` produces ordinary code text but Ollama reports
no native tools capability. It therefore cannot safely be the NOOA runtime.

## Consequences

- Coder never emits or impersonates NOOA tool calls.
- A controller decides if a code draft is useful; simple Java tool retrieval
  remains a direct controller action.
- `CodeDraft` is Pydantic-validated and checked by a narrow static policy
  before the controller may pass it to native NOOA `execute_python`.
- Docker remains the containment boundary; static checks are defence in depth.
- Java remains the sole source of valuation calculations; drafts may compose
  returned values but may not recreate DCF or FCFF/FCFE formulas.

## Rejected alternative

The previously explored text-to-tool protocol bridge is not a Phase 1 runtime
path. It conflates protocol repair with code meaning and was not reliable over
multiple turns.

## Keep/remove evidence

Keep the worker only if repeated synthetic evaluation shows Code Worker Utility
Rate and controller+worker completion success justify its added latency. Remove
it from the primary path if it mainly produces rejected drafts or does not
improve valid NOOA `return_result` completion.

The checked-in synthetic case set is `eval/datasets/controller_worker_cases.jsonl`.
The benchmark runner consumes sanitized opt-in trajectory outcomes and compares
Architecture A (controller only) and Architecture B (controller plus worker).
No results are committed until native NOOA runs exist.

Opt-in real acceptance commands are deliberately separate from CI:

```bash
scripts/sandbox/run-codeact.sh -m app.sandbox_controller_only_acceptance
scripts/sandbox/run-codeact.sh -m app.sandbox_controller_worker_acceptance
```

A successful process exit alone is insufficient: the resulting object must be
a native NOOA `return_result` validated as `ValuationReport`.

## Initial Architecture A observation

The first real Gemma-controller run reached the final NOOA return boundary but
submitted explanatory Markdown text where `return_result` required a
`ValuationReport`. NOOA/Pydantic rejected it. This is recorded as an
Architecture A failure, not a worker failure and not an acceptance success.
Architecture B is not run until the controller reliably obeys the typed final
return contract; invoking Coder cannot repair or own that contract.
