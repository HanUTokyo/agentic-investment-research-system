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
# Phase 1 controller–worker boundary

```text
NOOA ValuationAgent
  -> Gemma controller (native CodeAct tools and final ValuationReport)
       -> Java deterministic valuation APIs
       -> optional Router CODE request -> DeepSeek-Coder -> CodeDraft
  -> NOOA execute_python -> Docker sandbox
```

LangGraph is deliberately deferred: it will own future macro workflow state,
not the single-agent Phase 1 protocol. The Router selects models; it is not an
agent. DeepSeek-Coder is a code-draft worker, never a NOOA runtime model.
