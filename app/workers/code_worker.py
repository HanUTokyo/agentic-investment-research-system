"""Bounded text-code generation; this worker never speaks the NOOA tool protocol."""

from time import perf_counter
from typing import Protocol

from app.clients import RouterClient
from app.contracts import CodeDraft, CodeDraftTrace, CodeTask
from app.tools import validate_code_draft


class CodeWorker(Protocol):
    async def draft(
        self, task: CodeTask, *, research_id: str, iteration: int | None = None
    ) -> CodeDraft: ...


class RouterCodeWorker:
    """Request a CodeDraft from Router's explicit CODE route."""

    def __init__(self, router: RouterClient) -> None:
        self._router = router
        self.traces: list[CodeDraftTrace] = []

    async def draft(
        self, task: CodeTask, *, research_id: str, iteration: int | None = None
    ) -> CodeDraft:
        started = perf_counter()
        try:
            draft = await self._router.complete_structured(
                [
                    {
                        "role": "system",
                        "content": (
                            "Return JSON only with code, explanation, assumptions. Generate a bounded "
                            "Python draft only. Do not use imports, files, network, shell, DCF formulas, "
                            "or tool-call syntax. Use only named variables and available methods."
                        ),
                    },
                    {"role": "user", "content": task.model_dump_json()},
                ],
                CodeDraft,
                temperature=0,
                max_tokens=512,
                route_hint="code",
            )
            validate_code_draft(draft.code)
        except Exception:
            self.traces.append(
                CodeDraftTrace(
                    research_id=research_id,
                    validation_status="rejected",
                    latency_ms=(perf_counter() - started) * 1000,
                    iteration=iteration,
                )
            )
            raise
        self.traces.append(
            CodeDraftTrace(
                research_id=research_id,
                validation_status="accepted",
                latency_ms=(perf_counter() - started) * 1000,
                code_length=len(draft.code),
                iteration=iteration,
            )
        )
        return draft
