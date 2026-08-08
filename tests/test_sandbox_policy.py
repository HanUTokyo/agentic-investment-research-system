from pathlib import Path


def test_sandbox_runner_has_no_host_mount_or_direct_ollama_access() -> None:
    runner = Path("scripts/sandbox/run-codeact.sh").read_text()
    assert "--read-only" in runner
    assert "--cap-drop ALL" in runner
    assert "--network agent-restricted" in runner
    assert "-v " not in runner
    assert "ollama" not in runner.lower()
