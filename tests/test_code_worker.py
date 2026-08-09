import pytest

from app.contracts import CodeDraft, CodeTask, MethodSpec
from app.tools import CodePolicyError, validate_code_draft
from app.workers import RouterCodeWorker


class FakeRouter:
    def __init__(self, draft: CodeDraft) -> None:
        self.draft = draft
        self.calls: list[dict[str, object]] = []

    async def complete_structured(self, messages, response_model, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        assert response_model is CodeDraft
        return self.draft


def _task() -> CodeTask:
    return CodeTask(
        objective="Rank deterministic scenario values.",
        available_methods=[
            MethodSpec(
                name="run_valuation_scenario",
                signature="async (symbol, scenario_type)",
                description="Use Java valuation engine.",
            )
        ],
        known_variables={"symbol": "str"},
        constraints=["Do not calculate DCF."],
        expected_result="A sorted list of existing scenario outputs.",
    )


@pytest.mark.asyncio
async def test_worker_uses_explicit_code_route_and_validates_draft() -> None:
    router = FakeRouter(CodeDraft(code="values = sorted(values, reverse=True)"))
    worker = RouterCodeWorker(router)  # type: ignore[arg-type]

    draft = await worker.draft(_task(), research_id="research-1", iteration=2)

    assert draft.code.startswith("values")
    assert router.calls[0]["route_hint"] == "code"
    assert worker.traces[0].validation_status == "accepted"
    assert worker.traces[0].code_length == len(draft.code)


@pytest.mark.asyncio
async def test_worker_rejects_io_before_execution() -> None:
    worker = RouterCodeWorker(  # type: ignore[arg-type]
        FakeRouter(CodeDraft(code="import os\nos.system('whoami')"))
    )

    with pytest.raises(CodePolicyError):
        await worker.draft(_task(), research_id="research-1")

    assert worker.traces[0].validation_status == "rejected"


@pytest.mark.parametrize("code", ["open('x')", "exec('x=1')", "from os import system"])
def test_policy_rejects_unsafe_operations(code: str) -> None:
    with pytest.raises(CodePolicyError):
        validate_code_draft(code)
