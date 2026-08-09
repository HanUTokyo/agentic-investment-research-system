"""Bounded real-NOOA probes for ValuationAgent invariant recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from nooa.config import CodeActConfig
from nooa.decorators import strategy
from nooa.strategies import CodeActStrategy
from nooa.strategy_validation import InvariantError

from app.agents.valuation_agent import ValuationAgent
from app.contracts import Evidence, Uncertainty, ValuationReport, ValuationScenario

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

    def validate_final_report(self, report: ValuationReport) -> None:
        try:
            super().validate_final_report(report)
        except InvariantError as exc:
            self.invariant_feedback.append(str(exc).splitlines()[0])
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
