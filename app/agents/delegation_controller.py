"""Synthetic-only serial NOOA controller experiment; no financial tools."""

from __future__ import annotations

from time import perf_counter
from typing import Any, Literal

from nooa import Agent
from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy

from app.clients import RouterClient
from app.contracts import (
    ChatTask,
    CodeTaskText,
    DelegationResult,
    ReasonCodeDelegationResult,
    ReasonDelegationResult,
    ReasonTask,
    WorkerResult,
)


class SerialDelegationController(Agent):
    """Ministral controller. Its only capabilities are bounded Router workers."""

    def __init__(self, router: RouterClient, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._router = router
        self.worker_trace: list[WorkerResult] = []
        self._reason_calls = 0
        self._code_calls = 0

    async def delegate_reason(self, task: ReasonTask) -> WorkerResult:
        self._reason_calls += 1
        if self._reason_calls > 1:
            result = WorkerResult(
                ok=False,
                http_success=False,
                content_empty=True,
                error_type="reason_worker_attempt_limit_exceeded",
                route_hint="reason",
            )
            self.worker_trace.append(result)
            return result
        return await self._delegate("reason", task.prompt)

    async def delegate_code(self, task: CodeTaskText) -> WorkerResult:
        self._code_calls += 1
        if self._code_calls > 1:
            result = WorkerResult(
                ok=False,
                http_success=False,
                content_empty=True,
                error_type="code_worker_attempt_limit_exceeded",
                route_hint="code",
            )
            self.worker_trace.append(result)
            return result
        return await self._delegate("code", task.prompt)

    async def delegate_chat(self, task: ChatTask) -> WorkerResult:
        return await self._delegate("chat", task.prompt)

    async def _delegate(
        self, route_hint: Literal["reason", "code", "chat"], prompt: str
    ) -> WorkerResult:
        started = perf_counter()
        try:
            completion = await self._router.complete(
                [
                    {"role": "system", "content": "Return plain text only. Do not call tools."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=1024 if route_hint == "reason" else 256,
                route_hint=route_hint,
            )
            content = completion.content.strip()
            result = WorkerResult(
                ok=bool(content),
                http_success=True,
                content_empty=not bool(content),
                content=content or None,
                error_type=None if content else "empty_content",
                latency_ms=completion.latency_ms,
                route_hint=route_hint,
                model=completion.model,
            )
        except Exception as exc:  # Worker failure is typed evidence for controller.
            result = WorkerResult(
                ok=False,
                http_success=False,
                content_empty=True,
                error_type=type(exc).__name__,
                latency_ms=(perf_counter() - started) * 1000,
                route_hint=route_hint,
            )
        self.worker_trace.append(result)
        return result

    @strategy(
        CodeActStrategy(config=CodeActConfig(max_iterations=6, max_retries=1, max_tokens=1024))
    )
    async def solve(self, task: str) -> DelegationResult:
        """Solve the synthetic arithmetic task with strictly serial worker delegation.

        In one execute_python cell, call delegate_reason first and await it. Only
        after it completes call delegate_code, then delegate_chat. If any returned
        WorkerResult has ok=False, raise RuntimeError with that worker's error_type.
        Otherwise call return_result(DelegationResult(...)) from Python. Do not
        write prose or manually return a result outside native return_result.
        """
        ...

    @strategy(
        CodeActStrategy(config=CodeActConfig(max_iterations=3, max_retries=1, max_tokens=512))
    )
    async def solve_reason_only(self) -> ReasonDelegationResult:
        """Use exactly one worker and return only through native return_result.

        Call execute_python once. In that Python cell call and await exactly:
        `reason = await self.delegate_reason(ReasonTask(prompt="Return only the integer result of 17 * 25 + 8."))`.
        Do not call delegate_code or delegate_chat. If reason.ok is false, raise
        RuntimeError(reason.error_type or "reason worker failed"). Otherwise call
        `return_result(ReasonDelegationResult(worker_answer=reason.content, final_answer="433"))`.
        Do not emit prose and do not construct a result outside return_result.
        """
        ...

    @strategy(
        CodeActStrategy(config=CodeActConfig(max_iterations=4, max_retries=1, max_tokens=768))
    )
    async def solve_reason_code(self) -> ReasonCodeDelegationResult:
        """Use exactly two serial workers and native return_result only.

        In one execute_python cell, await delegate_reason first with the exact
        arithmetic prompt. Confirm it is ok. Only then await delegate_code with
        `Return only a minimal Python expression for 17 * 25 + 8.`. Confirm it
        is ok. Do not execute the code worker's output. Do not call chat. On
        either failure raise RuntimeError. Finally call
        return_result(ReasonCodeDelegationResult(reason_answer=reason.content,
        code_answer=code.content, final_answer="433")) from the cell.
        """
        ...
