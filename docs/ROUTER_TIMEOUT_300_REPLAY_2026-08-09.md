# Router 300-Second Timeout Replay

## Change

The local AI Router full profile changed only this setting:

```text
ollama.read_timeout_seconds: 120.0 -> 300.0
```

The Router was restarted and readiness returned HTTP 200. Gateway remains at
315 seconds and the Agent experiment remains bounded by its existing 720-second
overall timeout.

## Replays

The same runtime-forced `INVALID_EVIDENCE_PATH` probe was run twice after the
Router restart, without modifying the Controller prompt, R1 prompt,
`RecoveryPlan`, invariant, recovery runtime, Java tools, or model roles.

| Run ID | Invariant triggered | R1 called | Corrective Java-backed tool | Native report | Grounding |
|---|---:|---:|---:|---:|---:|
| `c47a69e3-63cf-4cf3-ba8f-391158791b4d` | no | no | yes | yes | yes |
| `76eecb73-2b7d-4bef-b410-55e52c31f960` | no | no | yes | yes | yes |

In both runs, Ministral chose `get_probe_valid_report()` before attempting the
controlled invalid candidate. Consequently there was no `InvariantError`, no
runtime-forced R1 request, and no `RecoveryPlan` to assess.

## Conclusion

The Router timeout change is active and removes the known 120-second upstream
cutoff. These two replays do not validate R1 recovery because the target branch
was not entered. Under the current constraint to change only the timeout, the
correct result is **not exercised**, rather than a claim that R1 or Controller
plan-to-action behavior passed or failed.
