# Security

No direct database, filesystem, shell, web-search, broker, or Ollama access is
provided to the agent. CodeAct is disabled unless launched through the restricted
Docker runner. The sandbox has a read-only root, non-root user, no mounts, no Docker
socket, resource limits, and a dedicated restricted network that should expose only
the Router and Java HTTP aliases. Logs omit prompts, payloads, tokens, and headers.

The current runner creates an internal Docker network. A future service-network
proxy must enforce the Java/Router allowlist before live CodeAct is enabled; until
then, only synthetic in-network smoke tests are permitted.

Real portfolio data, local databases, model files, and secrets are gitignored.
