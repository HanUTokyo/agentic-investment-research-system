from pathlib import Path

import pytest

from app.evaluation.coder_python import (
    DirectOllamaCoderCompletionClient,
    extract_python,
    load_cases,
    validate_python,
)


def test_coder_dataset_is_small_and_well_formed() -> None:
    cases = load_cases(Path("eval/datasets/coder_python_cases.json"))
    assert len(cases) == 11
    assert cases[0].case_id == "normalized_tags"
    assert cases[-1].case_id == "window_maximums"


def test_accepts_a_single_python_fence_with_surrounding_prose() -> None:
    source = extract_python(
        "Here is the implementation:\n```python\ndef normalized_tags(tags: list[str]) -> list[str]:\n"
        "    return []\n```\nIt handles empty lists."
    )
    validate_python(source, "normalized_tags")


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef normalized_tags(tags):\n    return []",
        "def other(tags):\n    return []",
        "def normalized_tags(tags):\n    return __import__('os').getcwd()",
    ],
)
def test_static_gate_rejects_unsafe_or_wrong_contract_source(source: str) -> None:
    with pytest.raises(ValueError):
        validate_python(source, "normalized_tags")


def test_direct_ollama_condition_is_explicitly_capability_only() -> None:
    client = DirectOllamaCoderCompletionClient("http://ollama.test", "coder")
    assert client._model == "coder"  # type: ignore[attr-defined]
