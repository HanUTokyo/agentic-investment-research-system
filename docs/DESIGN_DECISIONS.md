# Design decisions

- LangGraph is deferred to Phase 2: one NOOA specialist has no stateful graph need.
- NOOA supplies the specialist and CodeAct loop; LangChain is deliberately absent.
- Router remains the only model-routing policy. The logical `local-router` model
  goes to `/v1/chat/completions`; actual models are selected outside this service.
- Docker is the Phase 1 OS-level containment boundary. NOOA AST checks are not relied
  upon for security. OpenShell is the future preferred policy engine.
