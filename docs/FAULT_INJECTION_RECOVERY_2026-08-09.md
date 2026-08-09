# Controlled Invariant Fault-Injection Recovery

## Probe boundary

`FaultInjectedRuntimeRecoveryAgent` exists only under `app/experiments`. It
rejects the first report **after** normal `ValuationReport` grounding validation
has already passed. The injected `INVALID_EVIDENCE_PATH` changes no Java value,
source path, report field, or production `ValuationAgent` behavior. It never
repairs a report; the Controller must choose another tool call.

## Real sandbox result

Run ID: `867b2c2f-3738-4402-880e-346cb0be4e71`

| Field | Observed value |
|---|---|
| Fault injected | yes |
| Invariant | `INVALID_EVIDENCE_PATH` |
| Runtime-forced R1 | yes, exactly once |
| R1 route hint | `reason` |
| R1 budget | 1,024 tokens |
| R1 HTTP success | yes |
| R1 final content empty | yes |
| R1 state | `EMPTY_FINAL` |
| Valid `RecoveryPlan` | no |
| Controller received plan | no |
| Post-fault corrective tool | `get_probe_valid_report` |
| Native `return_result(ValuationReport)` | yes |
| Grounding validation | yes |
| Java calls | `get_compact_valuation` once (3,293 ms) |
| Coder / Gemma / scenario calls | 0 / 0 / 0 |
| Total latency | 543,215 ms |

## Interpretation

This probe deterministically entered the intended invariant branch and proves
that the runtime invokes R1 after it. The Router delivered a successful HTTP
completion, but DeepSeek R1 emitted no final `content` (its response stayed in
thinking), so strict JSON/Pydantic `RecoveryPlan` validation could not start.

Ministral did independently call the Java-backed corrective tool after the
fault and achieved a native, grounded report. That action cannot be attributed
to a RecoveryPlan because no plan was injected. The strict hierarchy acceptance
criterion is therefore **not passed**.

The current breakpoint is **R1 final-content production before plan validation**,
not `plan_to_action_execution`. That latter breakpoint can only be assessed once
the worker produces `VALID_PLAN`.
