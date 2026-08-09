# R1-Assisted Invariant Recovery — Real Run

## Scope

This bounded Phase 1 probe tests only `INVALID_EVIDENCE_PATH`. It permits one
Ministral Controller, one optional DeepSeek R1 recovery-planning call, and the
read-only Java valuation endpoint. Coder, Gemma, scenarios, LangGraph, report
rewriting, and parser fallback are excluded. Calls are serial.

## Contracts and boundary

The Controller owns the NOOA protocol and all tool execution. After a native
`return_result` is rejected, it may call `delegate_recovery_reason()` once.
R1 receives only concise invariant feedback and must return strict JSON matching
`RecoveryPlan`; the adapter applies `json.loads` plus Pydantic validation, with
no fence extraction, JSON repair, or fallback. R1 cannot access Java, NOOA tools,
or a `ValuationReport`.

The intended corrective action is `get_probe_valid_report(symbol)`, which returns
a Java-backed candidate with the original compact evidence paths. It does not
repair the invalid candidate or invent numerical facts.

## Real execution

Run ID: `12896323-72b4-4527-b8f0-ccf7d50420f3`  
Command: `scripts/sandbox/run-codeact.sh -m app.sandbox_r1_invariant_recovery_probe`  
Sandbox: non-root, read-only, internal Docker network; only controlled Java,
Router, and Controller proxy aliases were reachable.

| Field | Observed value |
|---|---|
| Total latency | 277,495 ms |
| Java calls | `get_compact_valuation` twice (3,314 ms; 2,038 ms) |
| Invariant feedback observed | `ERROR_TYPE: INVALID_EVIDENCE_PATH` |
| R1 called | No |
| R1 content empty | Not applicable |
| Recovery plan valid | No plan was requested |
| Recommended tool | Not applicable |
| Controller corrective tool called | No |
| Coder / Gemma / scenario calls | 0 / 0 / 0 |
| Native typed return | Failed |
| Grounding validation | Not reached |
| Recovery iterations | 1 invariant observation |

NOOA's final failure was:

```text
return_result validation failed after 2 attempts.
Last error:
return_result(result=...) - 'result' has wrong type.
Expected: ValuationReport
```

## Actual breakpoint

The Controller did reach the deterministic invariant and received feedback, but
it did not call `delegate_recovery_reason()` before retrying `return_result` with
the wrong type. Consequently this run **does not test R1 usefulness** and is not
a successful R1-assisted recovery. The breakpoint is Controller CodeAct
continuation/native typed-return use after the invariant observation, not Router,
R1, Java, or numerical grounding.

The required next experiment is to make the Controller's post-invariant action
space smaller (only the recovery capability and the Java-backed valid-candidate
capability) while still requiring the Controller itself to invoke them. It must
then be rerun before making a claim about whether R1 recovery planning helps.

## Verification

```text
/Users/kaihan/.local/bin/uv run ruff check .
/Users/kaihan/.local/bin/uv run ruff format --check .
/Users/kaihan/.local/bin/uv run pyright
/Users/kaihan/.local/bin/uv run pytest -q
```

All checks passed: Ruff, Pyright (0 errors), and pytest (39 passed, 1 skipped).
