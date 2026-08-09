# Phase 1 Compact-Contract Acceptance — 2026-08-09

## Implemented standard interface

The `ValuationAgent` now exposes deterministic Agent-facing contracts:

```text
Java valuation DTO
  → get_compact_valuation()
  → CompactValuationObservation

Java scenario evaluation DTO
  → run_compact_valuation_scenario()
  → CompactScenarioObservation
```

Both projections preserve Java facts and perform no valuation calculation. Full
Java DTOs remain behind the adapter boundary. The extra scenario tool remains
bounded to one evaluation per research run.

## Real AAPL acceptance result

- Run ID: `8883f072-5ddb-4248-abda-b7c4b90f157b`
- Total latency: 179,030.02 ms
- Coder calls: 0
- Gemma calls: 0
- R1 calls: 0
- Java compact valuation calls: 0
- Java scenario calls: 0
- Native `ValuationReport` return: failed

The Controller failed *before* it called `get_compact_valuation()`. Ministral
placed a Python code-fence string into `return_result` instead of using
NOOA's native `execute_python` tool. NOOA correctly rejected it:

```text
GenerationError: return_result(result=...) has wrong type
Expected: ValuationReport
Got: str
```

## Interpretation

This run does not invalidate the compact-contract design. The prior D replay
already demonstrated the live Java → compact observation → native typed-return
path. The current breakpoint precedes the tool call and is a Controller
tool-call/CodeAct protocol failure, not an HTTP, Java, R1, scenario, or
observation-size failure.

No fallback parser, Markdown extraction, manual report construction, or
financial calculation was used.
