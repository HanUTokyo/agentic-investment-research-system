#!/usr/bin/env sh
set -eu

# Docker is the Phase 1 isolation boundary. Deliberately no source/home mounts,
# Docker socket, credentials, or model-runtime hostname are made available.
# A service-network proxy may join this network and expose only Java and Router
# HTTP aliases; the host network is never used by this runner.
docker network inspect agent-restricted >/dev/null 2>&1 || \
  docker network create --internal agent-restricted >/dev/null
exec docker run --rm \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop ALL --security-opt no-new-privileges \
  --pids-limit 128 --memory 1024m --cpus 1.0 \
  --network agent-restricted \
  --user 10001:10001 \
  --env STOCK_PLATFORM_BASE_URL=http://stock-proxy:8080 \
  --env AI_ROUTER_BASE_URL=http://router-proxy:8080 \
  --env AGENT_HTTP_TIMEOUT_SECONDS="${AGENT_HTTP_TIMEOUT_SECONDS:-300}" \
  agentic-investment-research-sandbox "$@"
