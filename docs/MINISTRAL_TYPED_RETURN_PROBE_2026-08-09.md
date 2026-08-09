# Ministral 3 8B: NOOA typed-return probe

This is a single-run-per-level probe, not the required 20-run-per-level
benchmark. It used Router's `tool_model=ministral-3:8b`, Ollama native tools,
and the same NOOA CodeAct mechanism at every level.

| Level | Result | Latency |
|---|---|---:|
| TinyResult | schema-valid native completion | 40.0s |
| SimpleValuationResult | schema-valid native completion | 24.4s |
| ValuationReportLite | schema-valid native completion | 51.5s |
| NestedEvidenceReport | schema-valid native completion | 52.6s |
| Full ValuationReport | rejected: text passed where `ValuationReport` required | 73.4s |

Levels 2–4 completed through NOOA's valid inline `return_result()` path inside
`execute_python`, not necessarily a top-level tool call. The experiment metric
therefore counts a typed method completion as a native return success, while
retaining the top-level-call field for diagnostics.

The probe supports the hypothesis that schema complexity, rather than native
tool availability alone, is the primary issue. It does not establish a rate;
the 20-run benchmark remains required.
