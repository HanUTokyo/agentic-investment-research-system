"""Opt-in, payload-minimized NOOA trajectory capture for Phase 1 diagnosis."""

from __future__ import annotations

from collections import Counter
from typing import Any

from nooa.context_blocks.events import ToolCallEvent
from nooa.events import AfterTurn, BeforeTurn, LLMComplete, PythonOutput, TextOnlyReply


class ValuationTrajectoryRecorder:
    """Record controller actions and protocol observations without Java payloads."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self._current_turn: dict[str, Any] | None = None
        self._runtime_events: list[dict[str, Any]] = []
        self._actions_by_id: dict[str, dict[str, Any]] = {}

    def attach(self, event_manager: Any) -> None:
        event_manager.on("*", self._on_event)

    def _on_event(self, event: Any) -> None:
        if isinstance(event, BeforeTurn):
            turn = {
                "turn": event.turn_number,
                "actions": [],
                "python_observations": [],
                "text_only": [],
                "llm": None,
                "after": None,
            }
            self.turns.append(turn)
            self._current_turn = turn
        elif isinstance(event, LLMComplete):
            self._runtime_events.append(
                {
                    "type": "LLMComplete",
                    "model": event.model_name,
                    "prompt_tokens": event.prompt_tokens,
                    "completion_tokens": event.completion_tokens,
                    "tool_names": [item.get("function_name") for item in event.tool_calls],
                }
            )
            if self._current_turn is not None:
                self._current_turn["llm"] = self._runtime_events[-1]
        elif isinstance(event, TextOnlyReply) and self._current_turn is not None:
            self._current_turn["text_only"].append(
                {
                    "content": event.content[:4000],
                    "finish_reason": event.finish_reason,
                    "recovered": event.recovered,
                }
            )
        elif isinstance(event, ToolCallEvent):
            self._record_tool_call(event)
        elif isinstance(event, PythonOutput):
            self._record_python_output(event)
        elif isinstance(event, AfterTurn) and self._current_turn is not None:
            self._current_turn["after"] = {
                "is_final": event.is_final,
                "success": event.success,
                "exception_type": event.exception_type,
            }

    def finalize(self, event_manager: Any) -> dict[str, Any]:
        for _tag, event in event_manager.items():
            if isinstance(event, ToolCallEvent):
                action = self._actions_by_id.get(event.tool_call_id)
                if action is not None and event.result is not None:
                    action["result_status"] = event.result.result_status.value
                    action["result_preview"] = event.result.content[:1000]
        return {"turns": self.turns, "diagnosis": self._classify()}

    def _record_tool_call(self, event: ToolCallEvent) -> None:
        if self._current_turn is None:
            return
        arguments = event.arguments
        code = arguments.get("code") if event.name == "execute_python" else None
        action = {
            "tool": event.name,
            "code": code[:4000] if isinstance(code, str) else None,
            "result_status": None,
            "result_preview": None,
        }
        self._current_turn["actions"].append(action)
        self._actions_by_id[event.tool_call_id] = action

    def _record_python_output(self, event: PythonOutput) -> None:
        action = self._actions_by_id.get(event.tool_call_id)
        if action is None:
            return
        for turn in self.turns:
            if action in turn["actions"]:
                turn["python_observations"].append(
                    {
                        "execution_status": event.execution_status.value,
                        "error": event.error[:2000],
                        "stdout_length": len(event.stdout),
                        "stderr_length": len(event.stderr),
                        "explicit_return": event.explicit_return,
                    }
                )
                return

    def _classify(self) -> dict[str, Any]:
        actions = [action for turn in self.turns for action in turn["actions"]]
        codes = [action["code"] for action in actions if action["code"]]
        errors = [
            observation["error"]
            for turn in self.turns
            for observation in turn["python_observations"]
            if observation["error"]
        ]
        result_errors = [
            action.get("result_preview")
            for action in actions
            if action.get("result_status") == "error" and action.get("result_preview")
        ]
        repeated = [code for code, count in Counter(codes).items() if count > 1]
        text_only_turns = [turn["turn"] for turn in self.turns if turn["text_only"]]
        return {
            "candidate_categories": {
                "A_repeated_action": bool(repeated),
                "B_no_finalize_after_evidence": bool(actions)
                and not any(action["tool"] == "return_result" for action in actions),
                "C_illegal_python_or_tool": bool(errors),
                "D_invalid_return_schema": any(
                    "return_result" in item.lower() or "invalid result" in item.lower()
                    for item in result_errors
                ),
                "E_text_or_planning_drift": bool(text_only_turns),
                "F_observation_complexity": "not_determined_from_action_trace",
            },
            "repeated_code_count": len(repeated),
            "text_only_turns": text_only_turns,
            "execution_error_count": len(errors),
            "return_validation_error_count": len(result_errors),
        }
