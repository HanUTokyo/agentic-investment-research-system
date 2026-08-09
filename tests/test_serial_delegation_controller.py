import pytest

from app.agents.delegation_controller import SerialDelegationController
from app.clients.ai_router import RoutedCompletion
from app.contracts import ChatTask, CodeTaskText, ReasonTask


class FakeRouter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, _messages, **kwargs):
        route = kwargs["route_hint"]
        self.calls.append(route)
        return RoutedCompletion(
            content=f"{route} output",
            route=route,
            model=f"{route}-model",
            latency_ms=1.0,
            raw={},
        )


@pytest.mark.asyncio
async def test_explicit_delegations_are_typed_and_serial_when_awaited() -> None:
    router = FakeRouter()
    controller = SerialDelegationController(router, llm=object())  # type: ignore[arg-type]

    reason = await controller.delegate_reason(ReasonTask(prompt="reason"))
    code = await controller.delegate_code(CodeTaskText(prompt="code"))
    chat = await controller.delegate_chat(ChatTask(prompt="chat"))

    assert router.calls == ["reason", "code", "chat"]
    assert all(result.ok for result in [reason, code, chat])
    assert [item.route_hint for item in controller.worker_trace] == ["reason", "code", "chat"]


@pytest.mark.asyncio
async def test_empty_worker_content_is_returned_as_typed_failure() -> None:
    class EmptyRouter(FakeRouter):
        async def complete(self, _messages, **kwargs):
            return RoutedCompletion(content=" ", route="reason", model="r1", latency_ms=1.0, raw={})

    controller = SerialDelegationController(EmptyRouter(), llm=object())  # type: ignore[arg-type]
    result = await controller.delegate_reason(ReasonTask(prompt="reason"))

    assert result.ok is False
    assert result.error_type == "empty_content"


@pytest.mark.asyncio
async def test_reason_worker_cannot_be_retried_by_controller() -> None:
    router = FakeRouter()
    controller = SerialDelegationController(router, llm=object())  # type: ignore[arg-type]

    await controller.delegate_reason(ReasonTask(prompt="first"))
    retry = await controller.delegate_reason(ReasonTask(prompt="second"))

    assert router.calls == ["reason"]
    assert retry.error_type == "reason_worker_attempt_limit_exceeded"
