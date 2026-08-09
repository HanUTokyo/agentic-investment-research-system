# Architecture

The Java Investment Platform is the only source of financial facts and calculations.
This FastAPI service accesses it only through HTTP, then lets NOOA investigate those
typed results. Router is a separate service that selects local Ollama models; this
repository contains no classifier rules and makes no direct Ollama request.

```text
UI -> Java REST -> FastAPI service -> Ministral / NOOA controller
                    |                  |             |
                    +-- typed clients --+             +-> AI Router -> selected Ollama worker
                                                        (R1 / Coder / Gemma advisory only)
```

Phase 1 is intentionally sequential and supports tracked symbols only. LangGraph,
checkpointing, fixed multi-agent execution, and dynamic specialists begin in Phase 2+.
# Phase 1 controller–worker boundary

```text
Ministral / NOOA controller (the only typed-decision and final-result owner)
  -> Java deterministic valuation APIs
  -> optional bounded advisory capability
       -> AI Router (existing rules + Qwen classifier choose the worker model)
       -> R1 / Coder / Gemma raw advisory content
       -> Ministral reviews, adopts, or rejects it
  -> typed ValuationReport + Java grounding validation
```

LangGraph is deliberately deferred: it will own future macro workflow state,
not the single-agent Phase 1 protocol. The Router selects models; it is not an
agent. Workers never own NOOA protocol, call Java tools, execute code, or write
financial facts. In particular, Coder's raw draft may be reviewed by Ministral,
but is never executed or parsed into a report field.
