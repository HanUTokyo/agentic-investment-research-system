# Router Connectivity Probe — Sandbox to R1

## Scope

This change fixes only Router connectivity. It does not change Ministral, the
R1 prompt, `RecoveryPlan`, or the runtime-forced recovery strategy.

The Router source service was not running. It is now started locally on
the configured Router base URL with its existing `router.full.yaml` profile and forwards
to the configured local Ollama endpoint. The restricted sandbox
still reaches only `router-proxy`; the gateway is attached to the service bridge
and is configured to forward that alias to the configured Router base URL.

## Gateway correction

The gateway already allowed Router readiness and chat completions. It was
missing `POST /route`, which prevented the requested classifier probe. The
allowlist now contains only:

- `GET /health/ready`
- `POST /route`
- `POST /v1/chat/completions`

The runner forwards `AI_ROUTER_API_KEY` from its process environment without
hard-coding it or mounting credentials. The sandbox still has no host mount,
Docker socket, direct Ollama hostname, or unrestricted network access.

## Same-sandbox serial probe

`app.sandbox_router_connectivity_probe` ran from the normal restricted sandbox,
through the gateway, in this order:

| Step | Result | Latency |
|---|---|---:|
| Router `/health/ready` | ready | 705 ms |
| Router `/route` | `reason`, small-model classification | 17,855 ms |
| Router chat completion | non-empty `connected` | 10,478 ms |
| Router `route_hint=reason` / R1 | non-empty completion | 116,401 ms |

The R1 probe used 1,024 output tokens. Curl against the same Router confirmed
that the normal Router OpenAI response is non-empty at that budget.

## Unchanged recovery replay

The runtime-forced recovery was then rerun without altering its existing R1
request budget (`max_tokens=384`):

| Field | Result |
|---|---|
| Run ID | `2879c7c7-15a9-4f19-b615-42a60bd678aa` |
| Runtime recovery triggered | yes |
| R1 called | yes, once |
| Router connectivity | successful; no transport failure |
| R1 content | empty (`HTTP 200`) |
| Recovery plan | unavailable |
| Controller corrective tool | not called |
| Native typed return | failed after Controller retries |
| Total latency | 480,468 ms |

Direct Ollama inspection shows why this is distinct from connectivity: the
remote R1 model emits its early tokens in the `thinking` field. With 64 and 384
tokens it exhausted the generation budget before producing final `content`;
the Router's OpenAI adapter correctly exposes only final content. At 1,024
tokens it produced non-empty content.

## Current conclusion

Router connectivity is repaired and validated from the actual sandbox. The
remaining recovery blocker is not network configuration: it is the existing
R1 worker output budget/handling of R1 thinking. Per experiment scope, no
Controller, prompt, schema, or runtime change was made to address it.
