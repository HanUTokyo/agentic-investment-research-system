"""Bounded real-NOOA probes for ValuationAgent invariant recovery."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal, Protocol

from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy
from nooa.strategy_validation import InvariantError

from app.agents.valuation_agent import ValuationAgent
from app.contracts import Evidence, RecoveryPlan, Uncertainty, ValuationReport, ValuationScenario

ProbeCase = Literal[
    "missing_initial_evidence",
    "unsupported_numeric_claim",
    "invalid_evidence_path",
]


def _probe_postcondition(agent: Any, result: Any, _call: Any) -> None:
    if isinstance(agent, InvariantRecoveryValuationAgent):
        agent.validate_final_report(result)


class InvariantRecoveryValuationAgent(ValuationAgent):
    """Experimental subclass: deterministic candidates, Controller-owned retry."""

    def __init__(self, *args: Any, probe_case: ProbeCase, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.probe_case = probe_case
        self.corrective_actions: list[str] = []
        self.invariant_feedback: list[str] = []
        self._probe_observation = None
        self.last_invariant_feedback: str | None = None

    def validate_final_report(self, report: ValuationReport) -> None:
        try:
            super().validate_final_report(report)
        except InvariantError as exc:
            self.last_invariant_feedback = str(exc)
            self.invariant_feedback.append(self.last_invariant_feedback.splitlines()[0])
            raise

    async def get_probe_invalid_report(self, symbol: str) -> ValuationReport:
        """Return a Java-backed report candidate containing this probe's single defect.

        This tool never finalizes or repairs a report. The Controller must submit
        it, receive the deterministic error observation, then choose a correction.
        """
        if self.probe_case == "missing_initial_evidence":
            raw = await self._call(
                "get_probe_invalid_report", self._data_client.get_current_valuation(symbol)
            )
            from app.agents.valuation_projection import project_compact_valuation

            observation = project_compact_valuation(raw)
        else:
            observation = await self.get_compact_valuation(symbol)
        self._probe_observation = observation
        return self._report_from_observation(observation, invalid=True)

    async def get_probe_valid_report(self, symbol: str) -> ValuationReport:
        """Return the unmodified Java-backed candidate after an invariant observation."""
        if not self.initial_valuation_loaded:
            self._probe_observation = await self.get_compact_valuation(symbol)
        if self._probe_observation is None:
            self._probe_observation = await self.get_compact_valuation(symbol)
        self.corrective_actions.append("requested_valid_java_backed_report_candidate")
        return self._report_from_observation(self._probe_observation, invalid=False)

    def _report_from_observation(self, observation: Any, *, invalid: bool) -> ValuationReport:
        scenarios = [
            ValuationScenario(
                scenario_type=item.scenario_type,
                selected_model=item.selected_model,
                valid=item.valid,
                intrinsic_value_per_share=item.intrinsic_value_per_share,
                margin_of_safety_price=item.margin_of_safety_price,
                warnings=item.warnings,
            )
            for item in observation.scenarios
        ]
        evidence = [
            Evidence(
                claim="Java compact observation supplied the current market price.",
                source_path="get_compact_valuation.current_price",
                value=observation.current_price,
            )
        ]
        for item in observation.scenarios:
            path = f"get_compact_valuation.scenarios.{item.scenario_type}.intrinsic_value_per_share"
            if (
                invalid
                and self.probe_case == "invalid_evidence_path"
                and item.scenario_type == "BEAR"
            ):
                path = path.replace("per_share", "per_shair")
            evidence.append(
                Evidence(
                    claim=f"Java compact observation supplied {item.scenario_type} intrinsic value.",
                    source_path=path,
                    value=item.intrinsic_value_per_share,
                )
            )
        conclusion = "Java current price exceeds the Java base intrinsic value."
        if invalid and self.probe_case == "unsupported_numeric_claim":
            conclusion = f"Java current price is {observation.current_price}."
        return ValuationReport(
            symbol=observation.symbol,
            conclusion=conclusion,
            valuation_basis=observation.selected_model or "unavailable",
            engine_version=observation.engine_version,
            scenario_results=scenarios,
            evidence=evidence,
            uncertainties=[
                Uncertainty(
                    description="Java data-quality evidence remains the primary uncertainty.",
                    severity="high",
                    source_path="get_compact_valuation.material_warnings",
                )
            ],
            warnings=observation.material_warnings,
            tool_calls=self.tool_calls.copy(),
            trace_id=self.trace_id,
            generated_at=datetime.now(UTC),
        )

    @strategy(
        CodeActStrategy(
            config=CodeActConfig(
                max_iterations=6,
                max_retries=2,
                max_tokens=1024,
                postconditions=(_probe_postcondition,),
            )
        )
    )
    async def recover_invariant(self, symbol: str) -> ValuationReport:
        """Exercise one controlled invariant recovery case via native return_result.

        Case: {self.probe_case}. Do not call R1, Coder, Gemma, or scenarios.
        First call execute_python. For unsupported_numeric_claim and
        invalid_evidence_path, call get_probe_invalid_report(symbol), then call
        return_result(candidate) to deliberately receive the invariant feedback.
        For missing_initial_evidence, call get_probe_invalid_report(symbol) first;
        it deliberately does not satisfy initial_valuation_loaded. Then call
        return_result(candidate). After the deterministic error observation, call
        get_probe_valid_report(symbol) and call return_result(valid_candidate).
        Do not edit, parse, or repair either candidate. Do not emit prose.
        """
        ...


class RecoveryPlanningClient(Protocol):
    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any: ...


class RuntimeForcedRecoveryStrategy(CodeActStrategy):
    """Inject a typed R1 recovery observation after one recoverable invariant.

    The NOOA runtime invokes this hook only after the Controller has completed a
    turn whose native finalization raised ``INVALID_EVIDENCE_PATH``. The hook
    awaits R1 before the next Controller generation, preserving strict serial
    execution. It never invokes a Java capability or returns a report.
    """

    async def _process_tool_calls(self, *args: Any, **kwargs: Any) -> Any:
        result = await super()._process_tool_calls(*args, **kwargs)
        runtime = args[1]
        agent = runtime.agent
        if not isinstance(agent, RuntimeForcedR1RecoveryAgent):
            return result
        if not agent.should_force_runtime_recovery():
            return result

        await agent.force_runtime_recovery_plan()
        from nooa.events import Error

        runtime.event_manager.add(Error(content=agent.runtime_recovery_observation()))
        agent.controller_received_plan = agent.recovery_plan is not None
        return result


class R1AssistedInvariantRecoveryAgent(InvariantRecoveryValuationAgent):
    """Experimental Controller: R1 may plan recovery, never execute it."""

    def __init__(self, *args: Any, recovery_client: RecoveryPlanningClient, **kwargs: Any) -> None:
        super().__init__(*args, probe_case="invalid_evidence_path", **kwargs)
        self._recovery_client = recovery_client
        self.recovery_plan: RecoveryPlan | None = None
        self.r1_content_empty: bool | None = None
        self.r1_latency_ms: float | None = None
        self.r1_error_type: str | None = None

    async def delegate_recovery_reason(self) -> RecoveryPlan:
        """Ask R1 once to plan recovery from the latest invariant feedback."""
        if self.recovery_plan is not None or self.r1_error_type is not None:
            raise RuntimeError("recovery reason worker may be called only once")
        if not self.last_invariant_feedback:
            raise RuntimeError("no invariant feedback is available for recovery planning")
        started = perf_counter()
        try:
            completion = await self._recovery_client.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Return exactly one JSON object matching RecoveryPlan. You only plan; "
                            "do not calculate values, write a report, call tools, or use NOOA protocol. "
                            "For INVALID_EVIDENCE_PATH, recommend required_tool "
                            "get_probe_valid_report and explain that its Java-backed evidence path is required."
                        ),
                    },
                    {"role": "user", "content": self.last_invariant_feedback},
                ],
                temperature=0,
                max_tokens=384,
                route_hint="reason",
            )
            self.r1_latency_ms = completion.latency_ms
            content = completion.content.strip()
            self.r1_content_empty = not bool(content)
            if not content:
                raise ValueError("R1 returned empty content")
            self.recovery_plan = RecoveryPlan.model_validate(json.loads(content))
            return self.recovery_plan
        except Exception as exc:
            self.r1_error_type = type(exc).__name__
            self.r1_latency_ms = self.r1_latency_ms or (perf_counter() - started) * 1000
            raise RuntimeError(f"recovery reason worker failed: {self.r1_error_type}") from exc

    @strategy(
        CodeActStrategy(
            config=CodeActConfig(
                max_iterations=6,
                max_retries=2,
                max_tokens=1024,
                postconditions=(_probe_postcondition,),
            )
        )
    )
    async def recover_with_r1(self, symbol: str) -> ValuationReport:
        """Recover INVALID_EVIDENCE_PATH through R1 planning and Controller tool use.

        First call execute_python, obtain invalid_candidate via
        get_probe_invalid_report(symbol), then call return_result(invalid_candidate)
        to receive deterministic INVALID_EVIDENCE_PATH feedback. Only after that
        feedback, call delegate_recovery_reason() exactly once. If the returned
        RecoveryPlan.required_tool is not get_probe_valid_report, raise RuntimeError.
        Otherwise call get_probe_valid_report(symbol) yourself and native
        return_result(valid_candidate). R1 only proposes; it does not submit,
        modify, or calculate any report. Do not emit prose, call scenarios, or
        call any other worker.
        """
        ...


class RuntimeForcedR1RecoveryAgent(R1AssistedInvariantRecoveryAgent):
    """Probe agent where the runtime, rather than Ministral, requires R1."""

    def __init__(self, *args: Any, recovery_client: RecoveryPlanningClient, **kwargs: Any) -> None:
        super().__init__(*args, recovery_client=recovery_client, **kwargs)
        self.runtime_recovery_triggered = False
        self.controller_received_plan = False

    def should_force_runtime_recovery(self) -> bool:
        """Return true exactly once for the recoverable invariant under test."""
        return (
            not self.runtime_recovery_triggered
            and self.last_invariant_feedback is not None
            and self.last_invariant_feedback.startswith("ERROR_TYPE: INVALID_EVIDENCE_PATH")
        )

    async def force_runtime_recovery_plan(self) -> None:
        """Runtime-only trigger; this is not a Controller-selected capability."""
        self.runtime_recovery_triggered = True
        await self.delegate_recovery_reason()

    def runtime_recovery_observation(self) -> str:
        """Return concise typed recovery context for the next Controller turn."""
        if self.recovery_plan is None:
            return (
                "RUNTIME_RECOVERY_FAILURE\n"
                f"ERROR_TYPE: {self.r1_error_type or 'unknown'}\n"
                "ACTION: do not finalize; the required recovery plan was unavailable"
            )
        return (
            "RUNTIME_RECOVERY_PLAN\n"
            + self.recovery_plan.model_dump_json()
            + "\nACTION: execute the plan yourself. If required_tool is "
            "get_probe_valid_report, call await self.get_probe_valid_report(symbol) "
            "and call return_result(valid_candidate) from execute_python."
        )

    @strategy(
        RuntimeForcedRecoveryStrategy(
            config=CodeActConfig(
                max_iterations=6,
                max_retries=3,
                max_tokens=1024,
                postconditions=(_probe_postcondition,),
            )
        )
    )
    async def recover_with_runtime_forced_r1(self, symbol: str) -> ValuationReport:
        """Recover INVALID_EVIDENCE_PATH with a runtime-injected R1 plan.

        First use execute_python to obtain invalid_candidate through
        get_probe_invalid_report(symbol), then native return_result(invalid_candidate).
        The runtime will detect the resulting invariant feedback and add one
        RUNTIME_RECOVERY_PLAN observation before your next turn. Do not call R1.
        Read the plan, then execute its required Java-backed capability yourself:
        valid_candidate = await self.get_probe_valid_report(symbol), followed by
        return_result(valid_candidate) from execute_python. Do not edit candidates,
        construct reports, call scenarios, or emit prose.
        """
        ...
