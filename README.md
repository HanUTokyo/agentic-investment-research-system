# Agentic Investment Research System

A local-first, local-first AI research service that investigates a real, deterministic investment platform instead of replacing it with an LLM.

## The idea in two minutes

Financial facts, portfolio accounting, FCFF/FCFE valuation, sensitivity analysis, and reverse DCF remain in the Java Investment Platform. This independent FastAPI service gives a bounded NOOA valuation specialist typed, read-only HTTP tools. The existing AI Router selects among local Ollama models; the agent service never embeds classifier rules or directly calls Ollama.

```text
Java Investment Platform -> FastAPI typed adapters -> NOOA specialist -> AI Router -> local Ollama
                                      ^
                              deterministic evidence
```

Why these components: LangGraph (Phase 2) owns durable stateful research workflows; NOOA owns specialist autonomy and iterative CodeAct; the Router owns local model selection; Java owns every financial calculation. LangChain, cloud models, RAG, direct database access, and trade execution are intentionally out of scope.

## Current capability

Phase 0/1 provides a typed read-only integration layer, synthetic mock platform, health endpoints, a bounded `ValuationAgent`, and a Docker containment runner for future CodeAct execution. It supports tracked Java-platform symbols only and makes no persistent valuation or portfolio writes.

## Run

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run fastapi dev app/main.py
```

Copy `.env.example` to `.env` for local dependencies. CI and unit tests use only synthetic fixtures. See [architecture](docs/ARCHITECTURE.md), [API integration](docs/API_INTEGRATION.md), [security](docs/SECURITY.md), and [design decisions](docs/DESIGN_DECISIONS.md).

## Current limitations

- The live OpenAPI capture is pending a running Java server; the checked-in contract is schema-only.
- Router/NOOA CodeAct compatibility is an opt-in live test before real execution is enabled.
- LangGraph persistence, multi-agent research, dynamic specialists, and evaluation arrive in later phases.
- Licensing is intentionally undecided; no license is granted by this repository.
