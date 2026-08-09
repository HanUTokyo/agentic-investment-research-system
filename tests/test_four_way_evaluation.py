import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.agents.valuation_projection import project_compact_valuation
from app.clients.errors import UpstreamProtocolError
from app.contracts import NextActionDecision
from app.evaluation.four_way import (
    DirectStructuredClient,
    DirectTextClient,
    FrozenValuationClient,
    WorkerBundle,
    validate_public_synthetic_artifact,
)


@pytest.mark.asyncio
async def test_frozen_case_preserves_java_derived_compact_values() -> None:
    client, question = FrozenValuationClient.from_path(Path("fixtures/eval/phase1b_aapl.json"))
    compact = project_compact_valuation(await client.get_current_valuation("AAPL"))

    assert compact.symbol == "AAPL"
    assert compact.selected_model == "FCFE"
    assert compact.scenarios[1].intrinsic_value_per_share == 84
    assert "uncertainty" in question


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["```json\n{}\n```", "not-json", ""])
async def test_direct_client_rejects_non_strict_structured_output(content: str) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test/v1")
    direct = DirectStructuredClient(
        base_url="http://test/v1", model="synthetic", timeout_seconds=1, client=client
    )
    with pytest.raises((json.JSONDecodeError, UpstreamProtocolError, ValidationError)):
        await direct.generate("decision", [{"role": "user", "content": "x"}], NextActionDecision)

    assert direct.calls[0].success is False
    await client.aclose()


@pytest.mark.asyncio
async def test_direct_client_accepts_exact_schema_json() -> None:
    payload = {"action": "FINALIZE", "reason": "Evidence is sufficient."}

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test/v1")
    direct = DirectStructuredClient(
        base_url="http://test/v1", model="synthetic", timeout_seconds=1, client=client
    )
    result = await direct.generate(
        "decision", [{"role": "user", "content": "x"}], NextActionDecision
    )

    assert result.action == "FINALIZE"
    await client.aclose()


@pytest.mark.asyncio
async def test_direct_text_client_keeps_free_form_completion_verbatim() -> None:
    response_text = "A concise free-form answer."

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": response_text}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test/v1")
    direct = DirectTextClient(
        base_url="http://test/v1", model="synthetic", timeout_seconds=1, client=client
    )
    result = await direct.generate([{"role": "user", "content": "x"}])

    assert result == response_text
    assert direct.calls[0].response == response_text
    await client.aclose()


@pytest.mark.asyncio
async def test_worker_bundle_calls_every_route_in_strict_order() -> None:
    class FakeRouter:
        def __init__(self) -> None:
            self.routes: list[str] = []

        async def complete(self, _messages, **kwargs):
            from app.clients.ai_router import RoutedCompletion

            route = kwargs["route_hint"]
            self.routes.append(route)
            content = (
                '{"code":"unique_scenario_types = sorted(set(scenario_types))",'
                '"explanation":"draft","assumptions":[]}'
                if route == "code"
                else "review the warning"
            )
            return RoutedCompletion(content=content, route=route, model=route, latency_ms=1, raw={})

    client, question = FrozenValuationClient.from_path(Path("fixtures/eval/phase1b_aapl.json"))
    compact = project_compact_valuation(await client.get_current_valuation("AAPL"))
    router = FakeRouter()
    bundle = WorkerBundle(router)  # type: ignore[arg-type]
    reason, advisories = await bundle.collect(compact, question, "trace")

    assert router.routes == ["reason", "code", "chat"]
    assert reason is not None and reason.worker.ok
    assert [item["worker"] for item in advisories] == ["reason", "code", "chat"]
    assert advisories[1]["executed"] is False


def test_checked_in_evaluation_artifact_is_public_and_synthetic() -> None:
    for path in (
        Path("eval/results/phase1b_four_way_synthetic_aapl_2026-08-09.json"),
        Path("eval/results/raw_java_snapshot_three_model_2026-08-09.json"),
    ):
        validate_public_synthetic_artifact(json.loads(path.read_text()))
