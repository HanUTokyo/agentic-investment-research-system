from pathlib import Path


def test_sandbox_runner_has_no_host_mount_or_direct_ollama_access() -> None:
    runner = Path("scripts/sandbox/run-codeact.sh").read_text()
    assert "--read-only" in runner
    assert "--cap-drop ALL" in runner
    assert "--network agent-restricted" in runner
    assert "-v " not in runner
    assert "ollama" not in runner.lower()


def test_gateway_allows_only_required_router_connectivity_paths() -> None:
    gateway = Path("scripts/sandbox/gateway.py").read_text()
    assert '("GET", "/health/ready")' in gateway
    assert '("POST", "/route")' in gateway
    assert '("POST", "/v1/chat/completions")' in gateway
    assert "11434" not in gateway.split("ALLOWED =", 1)[1].split("class Gateway", 1)[0]
