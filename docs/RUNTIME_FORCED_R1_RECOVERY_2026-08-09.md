# Runtime-Forced R1 Recovery — Real Run

## Design under test

`RuntimeForcedRecoveryStrategy` extends NOOA `CodeActStrategy` at its async
tool-call boundary. When — and only when — a native `return_result` postcondition
has emitted `INVALID_EVIDENCE_PATH`, the runtime awaits one R1 request before it
permits the next Ministral generation. It then appends either a typed
`RUNTIME_RECOVERY_PLAN` observation or a concise recovery-failure observation to
the NOOA event stream.

This is deliberately not an automatic corrective action. R1 receives only the
structured invariant feedback and proposes a Pydantic `RecoveryPlan`. Ministral
alone must call `get_probe_valid_report()` and invoke native `return_result`.
Java remains the source of all numbers.

## Real sandbox execution

Run ID: `3f482e8b-fc15-495d-a945-c79e8aaffbd3`  
Command: `scripts/sandbox/run-codeact.sh -m app.sandbox_runtime_forced_r1_recovery_probe`

| Field | Observed value |
|---|---|
| Total latency | 149,885 ms |
| Invariant error | `INVALID_EVIDENCE_PATH` |
| Runtime recovery triggered | Yes |
| R1 called | Yes, exactly once |
| R1 HTTP completion/content | No completion; Router upstream network failure |
| Recovery plan valid | No |
| Controller received plan | No |
| Controller corrective tool called | No |
| Java calls | `get_compact_valuation` once (3,219 ms) |
| Coder / Gemma / scenario calls | 0 / 0 / 0 |
| Native typed return | Failed |
| Grounding | Not reached |

The gateway recorded an `OSError: [Errno 101] Network is unreachable` while
forwarding the R1 request to its configured Router host. Direct checks after the
run confirmed neither the local host nor `192.168.31.216:8000` was listening;
the remote Ollama endpoint on port 11434 was available, but direct Ollama use is
intentionally forbidden for this architecture.

## Result and breakpoint

The runtime-forcing mechanism works: it detected the recoverable invariant and
initiated precisely one serial R1 call. The experiment cannot evaluate
plan-to-action behavior because the Router infrastructure was unavailable before
R1 could return a `RecoveryPlan`.

The exact breakpoint is **Router connectivity before RecoveryPlan generation**,
not `plan → action execution failure`. The next valid run requires restoring the
existing AI Router on a reachable port 8000; it must not bypass the Router by
calling Ollama directly.

## Observability correction

`r1_content_empty` is now nullable: `true` means an HTTP completion explicitly
contained empty text, while `null` means no completion reached the client (as in
this run). This prevents a transport failure from being misclassified as R1's
known empty-content behavior.

## Verification

Ruff, Pyright, and pytest passed after the implementation change.
