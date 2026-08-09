# Runtime-Forced Recovery with R1 Budget 1024

## Controlled variable

This replay changes exactly one behavioral variable from the preceding runtime
recovery run:

```text
R1 RecoveryPlan max_tokens: 384 -> 1024
```

Ministral prompt, R1 prompt, `RecoveryPlan`, invariant, recovery runtime,
Router code, Java tools, and model roles are unchanged. Coder, Gemma, and
scenarios remain disabled.

## Explicit R1 completion states

The probe now distinguishes:

| State | Meaning |
|---|---|
| `NO_COMPLETION` | No usable Router completion due to network, HTTP, or timeout failure |
| `EMPTY_FINAL` | HTTP completion succeeded but final `content` is empty |
| `INVALID_PLAN` | Non-empty final content failed strict JSON/Pydantic `RecoveryPlan` validation |
| `VALID_PLAN` | Strict JSON/Pydantic `RecoveryPlan` validation succeeded |

No parser repair or fallback is used.

## Real replay

Run ID: `adb43222-0562-422c-95a0-89bac8eb4701`

| Field | Observed result |
|---|---|
| Invariant | `INVALID_EVIDENCE_PATH` |
| Runtime recovery triggered | yes |
| R1 called | yes, once |
| R1 configured budget | 1,024 tokens |
| R1 completion state | `NO_COMPLETION` |
| Router status for R1 request | HTTP 504 |
| Recovery plan | none |
| Controller received valid plan | no |
| Controller corrective tool | `get_probe_valid_report` was called |
| Native typed return | success |
| Grounding | success |
| Hierarchical recovery acceptance | **false** |
| Total latency | 460,725 ms |

The sandbox gateway shows the R1 Router request returned HTTP 504. Router's
existing `router.full.yaml` has a 120-second Ollama read timeout, while a
1,024-token DeepSeek R1 recovery completion can exceed it on this hardware.
The earlier independent connectivity probe did obtain non-empty R1 content at
1,024 tokens, but this fuller recovery-plan request crossed that existing
Router timeout.

## Conclusion

Increasing the Agent-side worker token budget alone does not produce a
`VALID_PLAN` while the Router's 120-second upstream read timeout remains in
place. This run therefore does **not** reach `RecoveryPlan -> Controller action
execution failure`: there was no valid plan to inject.

Although Ministral called the Java-backed corrective capability and completed a
grounded native report, that outcome cannot be attributed to the R1 hierarchy;
the strict experiment result remains unsuccessful because R1 did not return a
valid plan.
