#!/usr/bin/env sh
set -eu

docker network inspect agent-restricted >/dev/null 2>&1 || docker network create --internal agent-restricted >/dev/null
docker rm -f agent-codeact-gateway >/dev/null 2>&1 || true
docker run -d --name agent-codeact-gateway --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 128m --cpus 0.25 \
  --network agent-restricted --network-alias router-proxy --network-alias stock-proxy --network-alias controller-proxy \
  --env SANDBOX_ROUTER_HOST="${SANDBOX_ROUTER_HOST:-host.docker.internal}" \
  --env SANDBOX_STOCK_HOST="${SANDBOX_STOCK_HOST:-host.docker.internal}" \
  --env SANDBOX_CONTROLLER_HOST="${SANDBOX_CONTROLLER_HOST:-host.docker.internal}" \
  --env SANDBOX_UPSTREAM_TIMEOUT_SECONDS="${SANDBOX_UPSTREAM_TIMEOUT_SECONDS:-315}" \
  agentic-investment-research-gateway >/dev/null
docker network connect bridge agent-codeact-gateway
