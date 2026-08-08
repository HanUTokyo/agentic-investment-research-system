# Architecture

The Java Investment Platform is the only source of financial facts and calculations.
This FastAPI service accesses it only through HTTP, then lets NOOA investigate those
typed results. Router is a separate service that selects local Ollama models; this
repository contains no classifier rules and makes no direct Ollama request.

```text
UI -> Java REST -> FastAPI service -> NOOA ValuationAgent -> AI Router -> Ollama
                    |                  |
                    +-- typed clients --+-- Docker CodeAct sandbox
```

Phase 1 is intentionally sequential and supports tracked symbols only. LangGraph,
checkpointing, fixed multi-agent execution, and dynamic specialists begin in Phase 2+.
