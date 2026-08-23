import json
import math
import re
import time
from dataclasses import dataclass

from pydantic import ValidationError

from rtl_assistant.hardware_intent.compiler import (
    HardwareIntentCompilationError,
    compile_hardware_intent,
)
from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.hardware_intent import HardwareIntent
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.llm import (
    BehavioralObligation,
    BehavioralObligationSource,
    ClarificationQuestion,
    RequirementAnalysis,
    RequirementParseResult,
    RequirementStatus,
)
from rtl_assistant.spec.prompts import (
    ALLOWED_NONCRITICAL_ASSUMPTIONS,
    CRITICAL_AMBIGUITY_POLICY,
    HARDWARE_INTENT_PROMPT_VERSION,
    REQUIREMENT_ANALYSIS_PROMPT_VERSION,
    REQUIREMENT_PARSER_PROMPT_VERSION,
    build_hardware_intent_json_repair_prompt,
    build_hardware_intent_prompt,
    build_hardware_intent_repair_prompt,
    build_requirement_analysis_prompt,
    build_requirement_analysis_repair_prompt,
    build_requirement_parser_prompt,
    build_requirement_repair_prompt,
)

FAMILY_COUNTER = "counter"
FAMILY_ALU = "alu"
FAMILY_MUX = "mux"

NONCRITICAL_AMBIGUITY_IDS = {"clock_signal", "reset_signal", "module_name"}
GENERIC_STRUCTURAL_SEMANTIC_KEYS = {
    "input_width",
    "input_count",
    "output_width",
    "encoded_output_width",
    "input_representation",
    "select_mapping",
    "opcode_mapping",
    "signedness",
    "latency",
    "reset_presence",
    "reset_type",
    "reset_polarity",
    "reset_value",
    "state_width",
    "priority_direction",
    "no_active_input_behavior",
    "valid_output_presence",
    "count_direction",
    "overflow_behavior",
    "enable_behavior",
    "operations",
    "carry_behavior",
}
SIGNEDNESS_INSENSITIVE_OPERATION_TOKENS = {
    "ADD",
    "SUB",
    "BIT_AND",
    "BIT_OR",
    "BIT_XOR",
    "EQ",
    "NE",
    "SELECT",
}
SIGNEDNESS_SENSITIVE_OPERATION_TOKENS = {
    "LT",
    "LE",
    "GT",
    "GE",
    "ARITH_SHIFT_RIGHT",
    "SIGN_EXTEND",
}
SEMANTIC_KEY_ALIASES: dict[str, str] = {
    "counter_width": "state_width",
    "clock_edge": "clock_edge",
    "reset_presence": "reset_presence",
    "reset_type": "reset_type",
    "reset_polarity": "reset_polarity",
    "count_direction": "count_direction",
    "overflow_behavior": "overflow_behavior",
    "enable_behavior": "enable_behavior",
    "reset_value": "reset_value",
    "alu_width": "input_width",
    "alu_signedness": "signedness",
    "alu_operations": "operations",
    "opcode_mapping": "opcode_mapping",
    "result_width": "output_width",
    "carry_behavior": "carry_behavior",
    "mux_input_count": "input_count",
    "mux_data_width": "input_width",
    "mux_select_mapping": "select_mapping",
    "input_width": "input_width",
    "input_count": "input_count",
    "output_width": "output_width",
    "encoded_output_width": "encoded_output_width",
    "input_representation": "input_representation",
    "select_mapping": "select_mapping",
    "signedness": "signedness",
    "latency": "latency",
    "priority_direction": "priority_direction",
    "no_active_input_behavior": "no_active_input_behavior",
    "valid_output_presence": "valid_output_presence",
    "operations": "operations",
}

COUNTER_CANONICAL_QUESTIONS: dict[str, dict[str, object]] = {
    "counter_width": {
        "field": "width",
        "question": "How many bits should the counter use?",
        "reason": "Width determines the counter range.",
        "choices": [],
    },
    "clock_edge": {
        "field": "clock.edge",
        "question": "Which clock edge should update the counter?",
        "reason": "Clock edge changes sequential behavior.",
        "choices": ["positive", "negative"],
    },
    "reset_presence": {
        "field": "reset",
        "question": "Should the design have a reset?",
        "reason": "Reset behavior materially affects counter behavior.",
        "choices": ["yes", "no"],
    },
    "reset_type": {
        "field": "reset.type",
        "question": "Should the reset be synchronous or asynchronous?",
        "reason": "Reset timing changes the sequential hardware behavior.",
        "choices": ["synchronous", "asynchronous"],
    },
    "reset_polarity": {
        "field": "reset.polarity",
        "question": "Should the reset be active-high or active-low?",
        "reason": "Reset polarity changes when the hardware resets.",
        "choices": ["active_high", "active_low"],
    },
    "count_direction": {
        "field": "behavior.count_direction",
        "question": "Should the counter count up, down, or support both directions?",
        "reason": "Count direction changes the functional behavior.",
        "choices": ["up", "down", "both"],
    },
    "overflow_behavior": {
        "field": "behavior.overflow",
        "question": "What should happen on overflow?",
        "reason": "Overflow behavior changes the counter semantics.",
        "choices": ["wrap", "saturate", "other"],
    },
    "enable_behavior": {
        "field": "behavior.enable",
        "question": "Should the counter always update, or only when an enable signal is active?",
        "reason": "Enable behavior changes when the counter state updates.",
        "choices": ["always update", "use enable"],
    },
    "reset_value": {
        "field": "reset.reset_values",
        "question": "What value should the counter reset to?",
        "reason": "Reset value changes the initial visible counter state.",
        "choices": [],
    },
}

ALU_CANONICAL_QUESTIONS: dict[str, dict[str, object]] = {
    "alu_width": {
        "field": "width",
        "question": "What operand and result width should the ALU use?",
        "reason": "Width changes the arithmetic and logic behavior.",
        "choices": [],
    },
    "alu_signedness": {
        "field": "ports.signed",
        "question": "Should arithmetic operations be signed or unsigned?",
        "reason": "Signedness materially changes arithmetic behavior.",
        "choices": ["signed", "unsigned"],
    },
    "alu_operations": {
        "field": "behavior.operations",
        "question": "Which operations should the ALU support?",
        "reason": "Supported operations define the ALU functionality.",
        "choices": [],
    },
    "opcode_mapping": {
        "field": "behavior.opcode_mapping",
        "question": "How should control values map to ALU operations?",
        "reason": "Opcode mapping is required to avoid inventing control behavior.",
        "choices": [],
    },
    "result_width": {
        "field": "result.width",
        "question": "Should the ALU result width match the operand width or use a different width?",
        "reason": "Result width affects externally visible arithmetic behavior.",
        "choices": [],
    },
    "carry_behavior": {
        "field": "behavior.carry",
        "question": "How should carry or overflow outputs behave?",
        "reason": "Carry behavior changes the visible arithmetic interface.",
        "choices": [],
    },
}

MUX_CANONICAL_QUESTIONS: dict[str, dict[str, object]] = {
    "mux_input_count": {
        "field": "ports",
        "question": "How many data inputs should the multiplexer have?",
        "reason": "Input count determines the mux structure and select behavior.",
        "choices": [],
    },
    "mux_data_width": {
        "field": "width",
        "question": "What data width should the multiplexer use?",
        "reason": "Data width changes the interface and behavior.",
        "choices": [],
    },
    "mux_select_mapping": {
        "field": "behavior.select_mapping",
        "question": "How should select values map to the mux inputs?",
        "reason": "Select mapping is required to define the functional behavior.",
        "choices": [],
    },
}

CANONICAL_QUESTIONS_BY_FAMILY: dict[str, dict[str, dict[str, object]]] = {
    FAMILY_COUNTER: COUNTER_CANONICAL_QUESTIONS,
    FAMILY_ALU: ALU_CANONICAL_QUESTIONS,
    FAMILY_MUX: MUX_CANONICAL_QUESTIONS,
}

CANONICAL_ALIASES_BY_FAMILY: dict[str, dict[str, set[str]]] = {
    FAMILY_COUNTER: {
        "counter_width": {"counter_width", "counter width", "state width", "width", "bit width"},
        "clock_edge": {"clock_edge", "clock edge", "edge", "posedge/negedge"},
        "reset_presence": {"reset_presence", "reset", "reset behavior", "reset existence", "reset required"},
        "reset_type": {"reset_type", "reset type", "reset.type", "reset timing"},
        "reset_polarity": {"reset_polarity", "reset polarity", "reset.polarity", "active-high or active-low"},
        "count_direction": {"count_direction", "counter direction", "count direction"},
        "overflow_behavior": {"overflow_behavior", "overflow", "behavior.overflow", "wrap behavior"},
        "enable_behavior": {"enable_behavior", "enable", "behavior.enable"},
        "reset_value": {"reset_value", "reset value", "initial/reset state", "reset_values"},
        "clock_signal": {"clock_signal", "clock signal", "clock.signal"},
        "reset_signal": {"reset_signal", "reset signal", "reset.signal"},
    },
    FAMILY_ALU: {
        "alu_width": {"alu_width", "operand width", "width", "data width", "bit width"},
        "alu_signedness": {"alu_signedness", "signedness", "signed or unsigned", "ports.signed"},
        "alu_operations": {"alu_operations", "operations", "supported operations", "behavior.operations"},
        "opcode_mapping": {"opcode_mapping", "opcode", "control mapping", "behavior.opcode_mapping"},
        "result_width": {"result_width", "result width"},
        "carry_behavior": {"carry_behavior", "carry", "overflow semantics", "carry/overflow semantics"},
        "overflow_behavior": {"overflow_behavior", "overflow", "overflow semantics"},
    },
    FAMILY_MUX: {
        "mux_input_count": {"mux_input_count", "input count", "number of inputs", "ports"},
        "mux_data_width": {"mux_data_width", "width", "data width", "bit width"},
        "mux_select_mapping": {"mux_select_mapping", "select mapping", "behavior.select_mapping"},
    },
}


class AmbiguityPolicyInconsistencyError(ValueError):
    """Raised when local ambiguity policy would emit an impossible analysis state."""


@dataclass(frozen=True, slots=True)
class DerivedFact:
    """One deterministic fact resolved before asking the user for clarification."""

    key: str
    value: int | str | bool
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class AcceptedClarificationAnswer:
    """One validated clarification answer ready to be injected into enriched requirement text."""

    semantic_key: str
    value: str


@dataclass(frozen=True, slots=True)
class AnalyzedRequirement:
    """A requirement whose ambiguity analysis is complete and ready for HardwareSpec generation."""

    requirement: str
    analysis: RequirementAnalysis
    attempts: int
    raw_model_output: str
    duration_ms: int


class AIRequirementParser:
    """Parse natural-language hardware requirements into validated HardwareSpec objects."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self._last_validated_hardware_intent: HardwareIntent | None = None

    def get_last_validated_hardware_intent(self) -> HardwareIntent | None:
        """Return the exact validated HardwareIntent most recently passed toward deterministic lowering."""

        return self._last_validated_hardware_intent

    def parse(self, requirement: str) -> RequirementParseResult:
        """Convert a natural-language requirement into a validated HardwareSpec."""

        analysis_result = self._resolve_requirement_analysis(requirement)
        if isinstance(analysis_result, RequirementParseResult):
            return analysis_result
        return self.generate_hardware_spec(analysis_result)

    def analyze_requirement(self, requirement: str) -> AnalyzedRequirement | RequirementParseResult:
        """Run ambiguity analysis and return either a ready analysis or a structured parse result."""

        return self._resolve_requirement_analysis(requirement)

    def _resolve_requirement_analysis(self, requirement: str) -> AnalyzedRequirement | RequirementParseResult:
        """Run the full authoritative ambiguity-analysis pipeline for one requirement."""

        started_at = time.perf_counter()
        analysis_result = self._analyze_requirement(requirement)
        if isinstance(analysis_result, RequirementParseResult):
            analysis_result.duration_ms = int((time.perf_counter() - started_at) * 1000)
            return analysis_result

        analysis, analysis_attempts, analysis_output = analysis_result
        try:
            analysis = merge_with_local_ambiguity_policy(requirement, analysis)
        except AmbiguityPolicyInconsistencyError as exc:
            return RequirementParseResult(
                requirement=requirement,
                status=RequirementStatus.FAIL,
                hardware_spec=None,
                clarification_questions=[],
                unresolved_fields=[],
                assumptions=[],
                raw_model_output=analysis_output,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                attempts=analysis_attempts,
                validation_errors=[],
                error_type="AMBIGUITY_POLICY_INCONSISTENCY",
                error_message=str(exc),
                duration_ms=int((time.perf_counter() - started_at) * 1000),
            )

        try:
            analysis = finalize_requirement_analysis_state(analysis)
        except AmbiguityPolicyInconsistencyError as exc:
            return RequirementParseResult(
                requirement=requirement,
                status=RequirementStatus.FAIL,
                hardware_spec=None,
                clarification_questions=[],
                unresolved_fields=[],
                assumptions=analysis.assumptions,
                raw_model_output=analysis_output,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                attempts=analysis_attempts,
                validation_errors=[],
                error_type="AMBIGUITY_POLICY_INCONSISTENCY",
                error_message=str(exc),
                duration_ms=int((time.perf_counter() - started_at) * 1000),
            )

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if not analysis.ready:
            return RequirementParseResult(
                requirement=requirement,
                status=RequirementStatus.NEEDS_CLARIFICATION,
                hardware_spec=None,
                clarification_questions=analysis.clarification_questions,
                unresolved_fields=list(dict.fromkeys([*analysis.missing_critical, *analysis.ambiguous])),
                assumptions=analysis.assumptions,
                raw_model_output=analysis_output,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                attempts=analysis_attempts,
                validation_errors=[],
                error_type=None,
                error_message=None,
                duration_ms=duration_ms,
            )

        return AnalyzedRequirement(
            requirement=requirement,
            analysis=analysis,
            attempts=analysis_attempts,
            raw_model_output=analysis_output,
            duration_ms=duration_ms,
        )

    def generate_hardware_spec(self, analyzed_requirement: AnalyzedRequirement) -> RequirementParseResult:
        """Generate and validate a HardwareSpec once ambiguity analysis has reached READY."""

        self._last_validated_hardware_intent = None
        intent_result = self._generate_hardware_intent(
            analyzed_requirement.requirement,
            analyzed_requirement.analysis,
        )
        if isinstance(intent_result, RequirementParseResult):
            intent_result.duration_ms = analyzed_requirement.duration_ms
            intent_result.attempts += analyzed_requirement.attempts
            return intent_result

        hardware_intent, intent_attempts, raw_model_output = intent_result
        self._last_validated_hardware_intent = hardware_intent

        if hardware_intent.design_type.value != "combinational":
            spec_result = self._generate_hardware_spec_legacy(
                analyzed_requirement.requirement,
                analyzed_requirement.analysis,
            )
            if isinstance(spec_result, RequirementParseResult):
                spec_result.duration_ms = analyzed_requirement.duration_ms
                spec_result.attempts += analyzed_requirement.attempts + intent_attempts
                return spec_result

            hardware_spec, generation_attempts, legacy_raw_model_output = spec_result
            return RequirementParseResult(
                requirement=analyzed_requirement.requirement,
                status=RequirementStatus.READY,
                hardware_spec=hardware_spec,
                clarification_questions=[],
                unresolved_fields=[],
                assumptions=list(hardware_spec.behavior.assumptions),
                raw_model_output=legacy_raw_model_output,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                attempts=analyzed_requirement.attempts + intent_attempts + generation_attempts,
                validation_errors=[],
                error_type=None,
                error_message=None,
                duration_ms=analyzed_requirement.duration_ms,
            )

        try:
            hardware_spec = compile_hardware_intent(hardware_intent)
        except HardwareIntentCompilationError as exc:
            return RequirementParseResult(
                requirement=analyzed_requirement.requirement,
                status=RequirementStatus.FAIL,
                hardware_spec=None,
                clarification_questions=[],
                unresolved_fields=[],
                assumptions=hardware_intent.behavior.assumptions,
                raw_model_output=raw_model_output,
                provider=self.provider.provider_name,
                model=self.provider.model_name,
                attempts=analyzed_requirement.attempts + intent_attempts,
                validation_errors=[],
                error_type="INTENT_LOWERING_FAILED",
                error_message=str(exc),
                duration_ms=analyzed_requirement.duration_ms,
            )

        return RequirementParseResult(
            requirement=analyzed_requirement.requirement,
            status=RequirementStatus.READY,
            hardware_spec=hardware_spec,
            clarification_questions=[],
            unresolved_fields=[],
            assumptions=list(hardware_spec.behavior.assumptions),
            raw_model_output=raw_model_output,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            attempts=analyzed_requirement.attempts + intent_attempts,
            validation_errors=[],
            error_type=None,
            error_message=None,
            duration_ms=analyzed_requirement.duration_ms,
        )

    def parse_with_answers(self, original_requirement: str, answers: dict[str, str]) -> tuple[RequirementParseResult, str]:
        """Validate clarification answers, build enriched requirement text, and rerun parsing from that text."""

        first_pass = self._resolve_requirement_analysis(original_requirement)
        if isinstance(first_pass, RequirementParseResult) and first_pass.status == RequirementStatus.FAIL:
            return first_pass, original_requirement

        if isinstance(first_pass, AnalyzedRequirement):
            return (
                RequirementParseResult(
                    requirement=original_requirement,
                    status=RequirementStatus.FAIL,
                    hardware_spec=None,
                    clarification_questions=[],
                    unresolved_fields=[],
                    assumptions=first_pass.analysis.assumptions,
                    raw_model_output=first_pass.raw_model_output,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    attempts=first_pass.attempts,
                    validation_errors=[],
                    error_type="UNEXPECTED_CLARIFICATION_ANSWERS",
                    error_message="Clarification answers were provided, but the requirement did not require clarification.",
                    duration_ms=first_pass.duration_ms,
                ),
                original_requirement,
            )

        try:
            accepted_answers = validate_clarification_answers(
                original_requirement=original_requirement,
                answers=answers,
                clarification_questions=first_pass.clarification_questions,
            )
            enriched_requirement = build_enriched_requirement(
                original_requirement=original_requirement,
                accepted_answers=accepted_answers,
                clarification_questions=first_pass.clarification_questions,
            )
        except ValueError as exc:
            return (
                RequirementParseResult(
                    requirement=original_requirement,
                    status=RequirementStatus.FAIL,
                    hardware_spec=None,
                    clarification_questions=[],
                    unresolved_fields=[],
                    assumptions=first_pass.assumptions,
                    raw_model_output=first_pass.raw_model_output,
                    provider=first_pass.provider,
                    model=first_pass.model,
                    attempts=first_pass.attempts,
                    validation_errors=[],
                    error_type="INVALID_CLARIFICATION_ANSWERS",
                    error_message=str(exc),
                    duration_ms=first_pass.duration_ms,
                ),
                original_requirement,
            )

        if accepted_answers and enriched_requirement.strip() == original_requirement.strip():
            return (
                RequirementParseResult(
                    requirement=original_requirement,
                    status=RequirementStatus.FAIL,
                    hardware_spec=None,
                    clarification_questions=[],
                    unresolved_fields=[],
                    assumptions=first_pass.assumptions,
                    raw_model_output=first_pass.raw_model_output,
                    provider=first_pass.provider,
                    model=first_pass.model,
                    attempts=first_pass.attempts,
                    validation_errors=[],
                    error_type="CLARIFICATION_ENRICHMENT_FAILED",
                    error_message=(
                        "Clarification answers were accepted, but the enriched requirement remained identical to the "
                        "original requirement."
                    ),
                    duration_ms=first_pass.duration_ms,
                ),
                original_requirement,
            )

        second_pass = self._resolve_requirement_analysis(enriched_requirement)
        if isinstance(second_pass, RequirementParseResult):
            second_pass.requirement = original_requirement
            return second_pass, enriched_requirement

        final_result = self.generate_hardware_spec(second_pass)
        final_result.requirement = original_requirement
        return final_result, enriched_requirement

    def _analyze_requirement(
        self, requirement: str
    ) -> tuple[RequirementAnalysis, int, str] | RequirementParseResult:
        """Run ambiguity analysis before final HardwareSpec generation."""

        validation_errors: list[str] = []
        raw_model_output = ""

        for attempt_number in range(1, 3):
            if attempt_number == 1:
                prompt = build_requirement_analysis_prompt(requirement)
            else:
                prompt = build_requirement_analysis_repair_prompt(requirement, raw_model_output, validation_errors)

            llm_response = self.provider.generate(prompt)
            raw_model_output = llm_response.response_text

            if not llm_response.success:
                return RequirementParseResult(
                    requirement=requirement,
                    status=RequirementStatus.FAIL,
                    hardware_spec=None,
                    clarification_questions=[],
                    unresolved_fields=[],
                    assumptions=[],
                    raw_model_output=raw_model_output,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    attempts=attempt_number,
                    validation_errors=validation_errors,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                    duration_ms=llm_response.duration_ms,
                )

            json_object, json_error = extract_json_object(raw_model_output)
            if json_error is not None:
                validation_errors = [json_error]
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=[],
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="INVALID_ANALYSIS_JSON",
                        error_message="Requirement analysis output was not valid JSON after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            try:
                json_object = normalize_analysis_payload(json_object)
                analysis = RequirementAnalysis.model_validate(json_object)
            except ValidationError as exc:
                validation_errors = format_validation_errors(exc)
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=[],
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="REQUIREMENT_ANALYSIS_VALIDATION_FAILED",
                        error_message="Requirement analysis JSON did not satisfy the analysis schema after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            return analysis, attempt_number, raw_model_output

        return RequirementParseResult(
            requirement=requirement,
            status=RequirementStatus.FAIL,
            hardware_spec=None,
            clarification_questions=[],
            unresolved_fields=[],
            assumptions=[],
            raw_model_output=raw_model_output,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            attempts=2,
            validation_errors=validation_errors,
            error_type="ANALYSIS_RETRY_EXHAUSTED",
            error_message="Requirement analysis exhausted its retry budget.",
            duration_ms=None,
        )

    def _generate_hardware_intent(
        self, requirement: str, analysis: RequirementAnalysis
    ) -> tuple[HardwareIntent, int, str] | RequirementParseResult:
        """Generate and validate high-level HardwareIntent before deterministic semantic lowering."""

        validation_errors: list[str] = []
        raw_model_output = ""
        repair_kind: str | None = None
        enriched_requirement = enrich_requirement_for_generation(requirement, analysis)

        for attempt_number in range(1, 3):
            if attempt_number == 1:
                prompt = build_hardware_intent_prompt(enriched_requirement)
            elif repair_kind == "json":
                prompt = build_hardware_intent_json_repair_prompt(
                    enriched_requirement,
                    raw_model_output,
                    validation_errors[0] if validation_errors else "Unknown JSON parser error",
                )
            else:
                prompt = build_hardware_intent_repair_prompt(enriched_requirement, raw_model_output, validation_errors)

            llm_response = self.provider.generate(prompt)
            raw_model_output = llm_response.response_text

            if not llm_response.success:
                return RequirementParseResult(
                    requirement=requirement,
                    status=RequirementStatus.FAIL,
                    hardware_spec=None,
                    clarification_questions=[],
                    unresolved_fields=[],
                    assumptions=analysis.assumptions,
                    raw_model_output=raw_model_output,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    attempts=attempt_number,
                    validation_errors=validation_errors,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                    duration_ms=llm_response.duration_ms,
                )

            json_object, json_error = extract_json_object(raw_model_output)
            if json_error is not None:
                validation_errors = [json_error]
                repair_kind = "json"
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=analysis.assumptions,
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="INVALID_HARDWARE_INTENT_JSON",
                        error_message="Model output was not valid HardwareIntent JSON after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            try:
                json_object = normalize_hardware_intent_payload(json_object)
                envelope_errors = validate_hardware_intent_envelope(json_object)
                if envelope_errors:
                    validation_errors = envelope_errors
                    repair_kind = "validation"
                    if attempt_number == 2:
                        return RequirementParseResult(
                            requirement=requirement,
                            status=RequirementStatus.FAIL,
                            hardware_spec=None,
                            clarification_questions=[],
                            unresolved_fields=[],
                            assumptions=analysis.assumptions,
                            raw_model_output=raw_model_output,
                            provider=llm_response.provider,
                            model=llm_response.model,
                            attempts=attempt_number,
                            validation_errors=validation_errors,
                            error_type="INVALID_HARDWARE_INTENT_ENVELOPE",
                            error_message="Model output did not contain the complete authoritative HardwareIntent envelope after retry.",
                            duration_ms=llm_response.duration_ms,
                        )
                    continue
                hardware_intent = HardwareIntent.model_validate(json_object)
            except ValidationError as exc:
                validation_errors = format_validation_errors(exc)
                repair_kind = "validation"
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=analysis.assumptions,
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="HARDWARE_INTENT_INVALID",
                        error_message="Model output JSON did not satisfy the HardwareIntent schema after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            if hardware_intent.design_type.value == "combinational":
                try:
                    compile_hardware_intent(hardware_intent)
                except HardwareIntentCompilationError as exc:
                    validation_errors = [str(exc)]
                    repair_kind = "validation"
                    if attempt_number == 2:
                        return RequirementParseResult(
                            requirement=requirement,
                            status=RequirementStatus.FAIL,
                            hardware_spec=None,
                            clarification_questions=[],
                            unresolved_fields=[],
                            assumptions=analysis.assumptions,
                            raw_model_output=raw_model_output,
                            provider=llm_response.provider,
                            model=llm_response.model,
                            attempts=attempt_number,
                            validation_errors=validation_errors,
                            error_type="INTENT_LOWERING_FAILED",
                            error_message="HardwareIntent could not be lowered into valid semantic AST after retry.",
                            duration_ms=llm_response.duration_ms,
                        )
                    continue

            return hardware_intent, attempt_number, raw_model_output

        return RequirementParseResult(
            requirement=requirement,
            status=RequirementStatus.FAIL,
            hardware_spec=None,
            clarification_questions=[],
            unresolved_fields=[],
            assumptions=analysis.assumptions,
            raw_model_output=raw_model_output,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            attempts=2,
            validation_errors=validation_errors,
            error_type="HARDWARE_INTENT_RETRY_EXHAUSTED",
            error_message="Requirement parser exhausted its retry budget without producing a valid HardwareIntent.",
            duration_ms=None,
        )

    def _generate_hardware_spec_legacy(
        self, requirement: str, analysis: RequirementAnalysis
    ) -> tuple[HardwareSpec, int, str] | RequirementParseResult:
        """Legacy direct HardwareSpec generation path retained temporarily for sequential designs."""

        validation_errors: list[str] = []
        raw_model_output = ""
        enriched_requirement = enrich_requirement_for_generation(requirement, analysis)

        for attempt_number in range(1, 3):
            if attempt_number == 1:
                prompt = build_requirement_parser_prompt(enriched_requirement)
            else:
                prompt = build_requirement_repair_prompt(enriched_requirement, raw_model_output, validation_errors)

            llm_response = self.provider.generate(prompt)
            raw_model_output = llm_response.response_text

            if not llm_response.success:
                return RequirementParseResult(
                    requirement=requirement,
                    status=RequirementStatus.FAIL,
                    hardware_spec=None,
                    clarification_questions=[],
                    unresolved_fields=[],
                    assumptions=analysis.assumptions,
                    raw_model_output=raw_model_output,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    attempts=attempt_number,
                    validation_errors=validation_errors,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                    duration_ms=llm_response.duration_ms,
                )

            json_object, json_error = extract_json_object(raw_model_output)
            if json_error is not None:
                validation_errors = [json_error]
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=analysis.assumptions,
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="INVALID_LLM_JSON",
                        error_message="Model output was not valid JSON after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            semantic_constraint_error = detect_semantic_constraint_payload_inconsistency(json_object)
            if semantic_constraint_error is not None:
                validation_errors = [semantic_constraint_error]
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=analysis.assumptions,
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="HARDWARE_SPEC_VALIDATION_FAILED",
                        error_message="Model output JSON did not satisfy the HardwareSpec schema after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            try:
                hardware_spec = HardwareSpec.model_validate(json_object)
            except ValidationError as exc:
                validation_errors = format_validation_errors(exc)
                if attempt_number == 2:
                    return RequirementParseResult(
                        requirement=requirement,
                        status=RequirementStatus.FAIL,
                        hardware_spec=None,
                        clarification_questions=[],
                        unresolved_fields=[],
                        assumptions=analysis.assumptions,
                        raw_model_output=raw_model_output,
                        provider=llm_response.provider,
                        model=llm_response.model,
                        attempts=attempt_number,
                        validation_errors=validation_errors,
                        error_type="HARDWARE_SPEC_VALIDATION_FAILED",
                        error_message="Model output JSON did not satisfy the HardwareSpec schema after retry.",
                        duration_ms=llm_response.duration_ms,
                    )
                continue

            return hardware_spec, attempt_number, raw_model_output

        return RequirementParseResult(
            requirement=requirement,
            status=RequirementStatus.FAIL,
            hardware_spec=None,
            clarification_questions=[],
            unresolved_fields=[],
            assumptions=analysis.assumptions,
            raw_model_output=raw_model_output,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            attempts=2,
            validation_errors=validation_errors,
            error_type="PARSER_RETRY_EXHAUSTED",
            error_message="Requirement parser exhausted its retry budget without producing a valid HardwareSpec.",
            duration_ms=None,
        )


def apply_clarifications(original_requirement: str, answers: dict[str, str]) -> str:
    """Combine the original requirement with user-supplied clarification answers."""

    if not answers:
        return original_requirement.strip()

    lines = ["Original requirement:", original_requirement.strip(), "", "Clarifications:"]
    for key, value in answers.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


SEMANTIC_KEY_DISPLAY_LABELS: dict[str, str] = {
    "priority_direction": "Priority direction",
    "valid_output_presence": "Valid output presence",
    "input_width": "Input width",
    "input_count": "Input count",
    "output_width": "Output width",
    "encoded_output_width": "Encoded output width",
    "input_representation": "Input representation",
    "state_width": "State width",
    "reset_presence": "Reset presence",
    "reset_type": "Reset type",
    "reset_polarity": "Reset polarity",
    "reset_value": "Reset value",
    "clock_edge": "Clock edge",
    "count_direction": "Count direction",
    "overflow_behavior": "Overflow behavior",
    "enable_behavior": "Enable behavior",
    "signedness": "Signedness",
    "opcode_mapping": "Opcode mapping",
    "select_mapping": "Select mapping",
    "operations": "Operations",
    "latency": "Latency",
    "no_active_input_behavior": "No active input behavior",
}


def validate_clarification_answers(
    original_requirement: str,
    answers: dict[str, str],
    clarification_questions: list[ClarificationQuestion],
) -> list[AcceptedClarificationAnswer]:
    """Validate one answers payload against the current clarification contract."""

    if not clarification_questions:
        raise ValueError("Clarification answers were provided, but no clarification questions are currently active.")

    question_index: dict[str, ClarificationQuestion] = {}
    ordered_questions: list[ClarificationQuestion] = []
    seen_identities: set[str] = set()
    for question in clarification_questions:
        identity = question.semantic_key or question.id
        if identity not in seen_identities:
            ordered_questions.append(question)
            seen_identities.add(identity)
        question_index[question.id] = question
        if question.semantic_key is not None:
            question_index[question.semantic_key] = question

    accepted_by_semantic_key: dict[str, AcceptedClarificationAnswer] = {}
    for raw_key, raw_value in answers.items():
        question = question_index.get(raw_key.strip())
        if question is None:
            raise ValueError(f"Unknown clarification answer key '{raw_key}'.")

        semantic_key = question.semantic_key or question.id
        normalized_value = normalize_clarification_answer_value(raw_value, question)
        existing = accepted_by_semantic_key.get(semantic_key)
        if existing is not None and existing.value != normalized_value:
            raise ValueError(
                f"Conflicting clarification answers were provided for semantic key '{semantic_key}'."
            )
        accepted_by_semantic_key[semantic_key] = AcceptedClarificationAnswer(
            semantic_key=semantic_key,
            value=normalized_value,
        )

    for question in ordered_questions:
        if question.required and (question.semantic_key or question.id) not in accepted_by_semantic_key:
            raise ValueError(f"Missing required clarification answer for '{question.semantic_key or question.id}'.")

    detect_clarification_conflicts_with_existing_requirement(original_requirement, accepted_by_semantic_key)

    ordered_answers: list[AcceptedClarificationAnswer] = []
    emitted_semantic_keys: set[str] = set()
    for question in ordered_questions:
        identity = question.semantic_key or question.id
        if identity in accepted_by_semantic_key:
            ordered_answers.append(accepted_by_semantic_key[identity])
            emitted_semantic_keys.add(identity)
    for semantic_key, accepted_answer in accepted_by_semantic_key.items():
        if semantic_key not in emitted_semantic_keys:
            ordered_answers.append(accepted_answer)

    if answers and not ordered_answers:
        raise ValueError(
            "Clarification answers were accepted internally, but no canonical accepted-answer set survived normalization."
        )
    return ordered_answers


def normalize_clarification_answer_value(value: str, question: ClarificationQuestion) -> str:
    """Normalize one clarification answer using the question's declared contract."""

    stripped = value.strip()
    if not stripped:
        raise ValueError(f"Clarification answer for '{question.semantic_key or question.id}' cannot be empty.")

    if question.choices:
        for choice in question.choices:
            if stripped.casefold() == choice.strip().casefold():
                return choice.strip()
        raise ValueError(
            f"Invalid answer '{value}' for '{question.semantic_key or question.id}'. Allowed choices: {', '.join(question.choices)}."
        )

    return stripped


def build_enriched_requirement(
    original_requirement: str,
    accepted_answers: list[AcceptedClarificationAnswer],
    clarification_questions: list[ClarificationQuestion],
) -> str:
    """Build one deterministic enriched requirement text from validated clarification answers."""

    base_requirement, existing_answers = split_enriched_requirement_text(original_requirement)
    ordered_questions = dedupe_questions(clarification_questions)
    question_by_identity = {question.semantic_key or question.id: question for question in ordered_questions}

    merged_answers: dict[str, str] = dict(existing_answers)
    for answer in accepted_answers:
        existing_value = merged_answers.get(answer.semantic_key)
        if existing_value is not None and existing_value != answer.value:
            raise ValueError(
                f"Clarification answer for '{answer.semantic_key}' contradicts an existing clarified requirement value."
            )
        merged_answers[answer.semantic_key] = answer.value

    ordered_semantic_keys: list[str] = []
    for question in ordered_questions:
        identity = question.semantic_key or question.id
        if identity in merged_answers and identity not in ordered_semantic_keys:
            ordered_semantic_keys.append(identity)
    for semantic_key in merged_answers:
        if semantic_key not in ordered_semantic_keys:
            ordered_semantic_keys.append(semantic_key)

    if not ordered_semantic_keys:
        return base_requirement.strip()

    lines = [base_requirement.strip(), "", "Clarified requirements:"]
    for semantic_key in ordered_semantic_keys:
        label = clarification_display_label(semantic_key, question_by_identity.get(semantic_key))
        lines.append(f"- {label}: {merged_answers[semantic_key]}")
    return "\n".join(lines)


def split_enriched_requirement_text(requirement: str) -> tuple[str, dict[str, str]]:
    """Split one requirement into base text and an existing structured clarified-requirements block."""

    marker = "\n\nClarified requirements:\n"
    if marker not in requirement:
        return requirement.strip(), {}

    base_text, clarified_block = requirement.split(marker, 1)
    parsed_answers: dict[str, str] = {}
    for line in clarified_block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        payload = stripped[2:]
        if ":" not in payload:
            continue
        label, value = payload.split(":", 1)
        semantic_key = display_label_to_semantic_key(label.strip())
        parsed_answers[semantic_key] = value.strip()
    return base_text.strip(), parsed_answers


def clarification_display_label(semantic_key: str, question: ClarificationQuestion | None) -> str:
    """Return a stable human-readable label for one clarification semantic key."""

    if semantic_key in SEMANTIC_KEY_DISPLAY_LABELS:
        return SEMANTIC_KEY_DISPLAY_LABELS[semantic_key]
    if question is not None and question.field.strip():
        return question.field.strip().replace("_", " ").replace(".", " ").title()
    return semantic_key.replace("_", " ").title()


def display_label_to_semantic_key(label: str) -> str:
    """Convert one structured clarified-requirement label back into its semantic key."""

    normalized = " ".join(label.strip().lower().replace(".", " ").replace("_", " ").split())
    for semantic_key, display_label in SEMANTIC_KEY_DISPLAY_LABELS.items():
        if normalized == " ".join(display_label.lower().split()):
            return semantic_key
    return normalized.replace(" ", "_")


def detect_clarification_conflicts_with_existing_requirement(
    original_requirement: str,
    accepted_answers: dict[str, AcceptedClarificationAnswer],
) -> None:
    """Reject deterministic conflicts with an already enriched clarified-requirements block."""

    _, existing_answers = split_enriched_requirement_text(original_requirement)
    for semantic_key, answer in accepted_answers.items():
        existing_value = existing_answers.get(semantic_key)
        if existing_value is not None and existing_value != answer.value:
            raise ValueError(
                f"Clarification answer for '{semantic_key}' contradicts an existing clarified requirement value."
            )


def merge_with_local_ambiguity_policy(requirement: str, analysis: RequirementAnalysis) -> RequirementAnalysis:
    """Apply a conservative local ambiguity policy on top of LLM analysis."""

    family = detect_requirement_family(requirement)
    explicit = detect_explicit_details(requirement, family)
    derived_facts = derive_requirement_facts(requirement)
    shapes = detect_requirement_shapes(requirement.lower())
    behavioral_obligations = dedupe_behavioral_obligations(
        [*analysis.behavioral_obligations, *detect_behavioral_obligations(requirement)]
    )
    explicit_keys = normalize_explicit_semantic_keys(explicit, family=family, shapes=shapes)
    normalized = normalize_requirement_analysis(
        analysis,
        family=family,
        explicit=explicit,
        derived_facts=derived_facts,
        shapes=shapes,
        behavioral_obligations=behavioral_obligations,
    )
    local_questions = derive_local_clarifications(
        requirement,
        family=family,
        explicit=explicit,
        derived_facts=derived_facts,
        shapes=shapes,
    )

    merged_questions: dict[str, ClarificationQuestion] = {
        question_identity(question): question for question in normalized.clarification_questions
    }
    for question in local_questions:
        identity = question_identity(question)
        if identity in merged_questions:
            merged_questions[identity] = merge_questions(merged_questions[identity], question, prefer_new=True)
        else:
            merged_questions[identity] = question

    unresolved_ids = list(
        dict.fromkeys(
            [
                *filter_resolved_labels(
                    normalized.missing_critical,
                    derived_facts=derived_facts,
                    shapes=shapes,
                    family=family,
                    explicit=explicit,
                    behavioral_obligations=behavioral_obligations,
                ),
                *(
                    canonical_semantic_identity(question.semantic_key or question.id, family=family, shapes=shapes)
                    for question in merged_questions.values()
                ),
            ]
        )
    )
    unresolved_ids = [item for item in unresolved_ids if item not in explicit_keys and item not in NONCRITICAL_AMBIGUITY_IDS]

    if not unresolved_ids and not merged_questions:
        return RequirementAnalysis(
            ready=True,
            explicitly_specified=list(dict.fromkeys([*normalized.explicitly_specified, *sorted(explicit)])),
            safely_inferred=normalized.safely_inferred,
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=normalized.assumptions,
            behavioral_obligations=behavioral_obligations,
        )

    return RequirementAnalysis(
        ready=False,
        explicitly_specified=list(dict.fromkeys([*normalized.explicitly_specified, *sorted(explicit)])),
        safely_inferred=normalized.safely_inferred,
        missing_critical=unresolved_ids,
        ambiguous=unresolved_ids,
        clarification_questions=list(merged_questions.values()),
        assumptions=normalized.assumptions,
        behavioral_obligations=behavioral_obligations,
    )


def derive_local_clarifications(
    requirement: str,
    family: str | None,
    explicit: set[str],
    derived_facts: dict[str, DerivedFact],
    shapes: set[str],
) -> list[ClarificationQuestion]:
    """Derive conservative clarification questions for obviously underspecified prompts."""

    text = requirement.lower()
    questions: list[ClarificationQuestion] = []
    explicit_keys = normalize_explicit_semantic_keys(explicit, family=family, shapes=shapes)

    if family == FAMILY_COUNTER:
        if "counter_width" not in explicit and "counter_width" not in derived_facts:
            questions.append(make_canonical_question(FAMILY_COUNTER, "counter_width"))
        if "clock_edge" not in explicit:
            questions.append(make_canonical_question(FAMILY_COUNTER, "clock_edge"))
        if "count_direction" not in explicit:
            questions.append(make_canonical_question(FAMILY_COUNTER, "count_direction"))
        if "overflow_behavior" not in explicit:
            questions.append(make_canonical_question(FAMILY_COUNTER, "overflow_behavior"))
        if "reset_presence" not in explicit:
            questions.append(make_canonical_question(FAMILY_COUNTER, "reset_presence"))
        elif text_mentions_reset(text):
            if "reset_type" not in explicit:
                questions.append(make_canonical_question(FAMILY_COUNTER, "reset_type"))
            if "reset_polarity" not in explicit:
                questions.append(make_canonical_question(FAMILY_COUNTER, "reset_polarity"))
            if "reset_value" not in explicit:
                questions.append(make_canonical_question(FAMILY_COUNTER, "reset_value"))

    if family == FAMILY_ALU:
        if "alu_width" not in explicit and "alu_width" not in derived_facts:
            questions.append(make_canonical_question(FAMILY_ALU, "alu_width"))
        if "alu_operations" not in explicit and "operations" not in derived_facts:
            questions.append(make_canonical_question(FAMILY_ALU, "alu_operations"))
        if "alu_signedness" not in explicit and is_semantic_key_applicable(
            "signedness",
            family=family,
            shapes=shapes,
            explicit=explicit,
            derived_facts=derived_facts,
        ):
            questions.append(make_canonical_question(FAMILY_ALU, "alu_signedness"))
        if has_multiple_operations(text) and "opcode_mapping" not in explicit:
            questions.append(make_canonical_question(FAMILY_ALU, "opcode_mapping"))

    if family == FAMILY_MUX:
        if "mux_input_count" not in explicit and "mux_input_count" not in derived_facts:
            questions.append(make_canonical_question(FAMILY_MUX, "mux_input_count"))
        if "mux_data_width" not in explicit and "mux_data_width" not in derived_facts:
            questions.append(make_canonical_question(FAMILY_MUX, "mux_data_width"))
        if "mux_select_mapping" not in explicit:
            questions.append(make_canonical_question(FAMILY_MUX, "mux_select_mapping"))

    if "priority_encoder_like" in shapes:
        if "priority_direction" not in explicit and "priority_direction" not in derived_facts:
            questions.append(
                ClarificationQuestion(
                    id="priority_direction",
                    field="priority_direction",
                    semantic_key="priority_direction",
                    question="What is the direction of priority encoding?",
                    reason="Priority encoders need a defined winning direction when multiple inputs are asserted.",
                    required=True,
                    choices=["Lowest to highest", "Highest to lowest"],
                    default=None,
                )
            )
        if "valid_output_presence" not in explicit and "valid_output_presence" not in derived_facts:
            questions.append(
                ClarificationQuestion(
                    id="valid_output_presence",
                    field="valid_output_presence",
                    semantic_key="valid_output_presence",
                    question="Should the encoder indicate when there is a valid output?",
                    reason="A priority encoder may or may not expose a separate valid output when no input is asserted.",
                    required=True,
                    choices=["Yes", "No"],
                    default=None,
                )
            )

    if "signedness_relevant" in derived_facts and "signedness" not in explicit_keys:
        questions.append(build_signedness_clarification_question(requirement))

    return dedupe_questions(questions)


def detect_requirement_family(requirement: str) -> str | None:
    """Detect the primary supported module family from the requirement text."""

    text = requirement.lower()
    if re.search(r"\bcounter\b", text):
        return FAMILY_COUNTER
    if re.search(r"\balu\b", text):
        return FAMILY_ALU
    if re.search(r"\bmultiplexer\b|\bmux\b", text):
        return FAMILY_MUX
    return None


BEHAVIOR_RULE_PATTERN = re.compile(
    r"^\s*(?P<target>[a-z_][a-z0-9_]*)\s*"
    r"(?:=|equals?|is|represents?|should\s+(?:be|equal|represent))\s*"
    r"(?P<when_true>.+?)\s+\b(?:when|if)\b\s+(?P<conditional_tail>.+?)\s*$",
    re.IGNORECASE,
)
BEHAVIOR_OTHERWISE_PATTERNS = (
    re.compile(
        r"^(?P<condition>.+?),\s*(?:and\s+)?(?P<when_false>.+?)\s+otherwise$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<condition>.+?),?\s*(?:otherwise|else)\s+(?P<when_false>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?P<condition>.+?)(?:,\s*)?\s+and\s+(?:should\s+be\s+)?"
        r"(?P<when_false>.+?)\s+for\s+(?:every|all)\s+other\b.+$",
        re.IGNORECASE,
    ),
)


def detect_behavioral_obligations(requirement: str) -> list[BehavioralObligation]:
    """Conservatively preserve clear conditional behavior rules from requirement and clarification text."""

    base_requirement, clarification_answers = split_enriched_requirement_text(requirement)
    obligations = _detect_behavioral_obligations_in_text(
        base_requirement,
        source=BehavioralObligationSource.EXPLICIT_REQUIREMENT,
    )
    for semantic_key, value in clarification_answers.items():
        obligations.extend(
            _detect_behavioral_obligations_in_text(
                value,
                source=BehavioralObligationSource.CLARIFICATION,
                evidence_prefix=f"{semantic_key}: ",
            )
        )
    return dedupe_behavioral_obligations(obligations)


def _detect_behavioral_obligations_in_text(
    text: str,
    *,
    source: BehavioralObligationSource,
    evidence_prefix: str = "",
) -> list[BehavioralObligation]:
    obligations: list[BehavioralObligation] = []
    for raw_statement in re.split(r"[.;\n]+", text):
        statement = " ".join(raw_statement.strip().split())
        if not statement:
            continue
        match = BEHAVIOR_RULE_PATTERN.match(statement)
        if match is None:
            continue

        condition = match.group("conditional_tail").strip().rstrip(",")
        when_false: str | None = None
        for otherwise_pattern in BEHAVIOR_OTHERWISE_PATTERNS:
            otherwise_match = otherwise_pattern.match(match.group("conditional_tail").strip())
            if otherwise_match is not None:
                condition = otherwise_match.group("condition").strip().rstrip(",")
                when_false = otherwise_match.group("when_false").strip()
                break

        obligations.append(
            BehavioralObligation(
                target=match.group("target"),
                condition=condition,
                when_true=match.group("when_true"),
                when_false=when_false,
                complete=when_false is not None,
                source=source,
                evidence=f"{evidence_prefix}{statement}",
            )
        )
    return obligations


def dedupe_behavioral_obligations(
    obligations: list[BehavioralObligation],
) -> list[BehavioralObligation]:
    deduped: dict[tuple[str, str | None, str, str | None], BehavioralObligation] = {}
    for obligation in obligations:
        identity = (
            obligation.target.casefold(),
            obligation.condition.casefold() if obligation.condition is not None else None,
            obligation.when_true.casefold(),
            obligation.when_false.casefold() if obligation.when_false is not None else None,
        )
        deduped.setdefault(identity, obligation)
    return list(deduped.values())


def behavioral_obligation_semantic_keys(obligation: BehavioralObligation) -> set[str]:
    """Return generic semantic identities resolved by one complete behavior obligation."""

    target = obligation.target.casefold()
    return {f"{target}_behavior", f"{target}_output_behavior"}


def behavior_target_from_semantic_key(semantic_key: str | None) -> str | None:
    """Recover the declared target from a generic structured behavior semantic key."""

    if not semantic_key:
        return None
    normalized = semantic_key.strip().lower().replace(".", "_").replace(" ", "_")
    for suffix in ("_output_behavior", "_behavior"):
        if normalized.endswith(suffix):
            target = normalized[: -len(suffix)]
            if re.fullmatch(r"[a-z_][a-z0-9_]*", target):
                return target
    return None


def detect_explicit_behavior_rules(text: str) -> set[str]:
    """Return behavior semantic keys only for complete, explicitly specified conditional rules."""

    explicit: set[str] = set()
    for obligation in detect_behavioral_obligations(text):
        if obligation.complete:
            explicit.update(behavioral_obligation_semantic_keys(obligation))
    return explicit


def is_implementation_detail_question(
    question: "ClarificationQuestion",
    family: str | None,
) -> bool:
    lowered = " ".join(
        part
        for part in (
            question.semantic_key or "",
            question.question or "",
            question.reason or "",
        )
        if part
    ).lower()
    family_text = (family or "").lower()
    primitive_keywords = ("mux", "decoder", "arbiter")
    generic_keywords = (
        "internal stage",
        "pipeline stage",
        "topology",
        "implementation detail",
        "internal structure",
    )
    if any(keyword in lowered for keyword in generic_keywords):
        return True
    for keyword in primitive_keywords:
        if keyword in lowered and keyword not in family_text:
            return True
    return False


def is_implementation_detail_semantic_key(
    semantic_key: str | None,
    family: str | None,
) -> bool:
    if not semantic_key:
        return False
    lowered = semantic_key.lower()
    family_text = (family or "").lower()
    primitive_keywords = ("mux", "decoder", "arbiter")
    generic_keywords = ("stage", "topology", "implementation")
    if any(keyword in lowered for keyword in generic_keywords):
        return True
    for keyword in primitive_keywords:
        if keyword in lowered and keyword not in family_text:
            return True
    return False


def detect_explicit_details(requirement: str, family: str | None) -> set[str]:
    """Detect explicitly specified critical concepts from the requirement text."""

    explicit = detect_explicit_behavior_rules(requirement)
    text = requirement.lower()

    if family == FAMILY_COUNTER:
        if has_any_bit_width(text):
            explicit.add("counter_width")
        if has_clock_edge(text):
            explicit.add("clock_edge")
        if text_mentions_reset(text):
            explicit.add("reset_presence")
        if has_reset_type(text):
            explicit.add("reset_type")
        if has_reset_polarity(text):
            explicit.add("reset_polarity")
        if has_counter_direction(text):
            explicit.add("count_direction")
        if has_overflow_behavior(text):
            explicit.add("overflow_behavior")
        if has_reset_value(text):
            explicit.add("reset_value")

    if family == FAMILY_ALU:
        if has_any_bit_width(text):
            explicit.add("alu_width")
        if has_operations(text):
            explicit.add("alu_operations")
        if has_signedness(text):
            explicit.add("alu_signedness")

    if has_opcode_mapping(text):
        explicit.add("opcode_mapping")

    if family == FAMILY_MUX:
        if has_mux_input_count(text):
            explicit.add("mux_input_count")
        if has_any_bit_width(text):
            explicit.add("mux_data_width")
        if has_select_mapping(text):
            explicit.add("mux_select_mapping")

    if has_signedness(text):
        explicit.add("signedness")

    if re.search(r"\bhighest(?:-index)?\s+to\s+lowest\b|\bhighest\s+priority\b|\bmsb\s+first\b", text):
        explicit.add("priority_direction")
    if re.search(r"\blowest(?:-index)?\s+to\s+highest\b|\blowest\s+priority\b|\blsb\s+first\b", text):
        explicit.add("priority_direction")
    if re.search(r"\bvalid output\b|\bvalid signal\b|\bvalid flag\b", text):
        explicit.add("valid_output_presence")

    return explicit


def normalize_requirement_analysis(
    analysis: RequirementAnalysis,
    family: str | None,
    explicit: set[str],
    derived_facts: dict[str, DerivedFact],
    shapes: set[str],
    behavioral_obligations: list[BehavioralObligation] | None = None,
) -> RequirementAnalysis:
    """Normalize LLM-produced ambiguity labels into canonical semantic concepts.

    Final readiness is derived from the remaining unresolved evidence after deterministic
    normalization, grounding, and derivation filters have run. The LLM's original
    ready flag is treated as advisory input rather than the final authority.
    """
    if behavioral_obligations is None:
        behavioral_obligations = list(analysis.behavioral_obligations)
    explicit_keys = normalize_explicit_semantic_keys(explicit, family=family, shapes=shapes)

    initial_missing = normalize_labels([*analysis.missing_critical, *analysis.ambiguous], family=family)
    normalized_missing = filter_resolved_labels(
        initial_missing,
        derived_facts=derived_facts,
        shapes=shapes,
        family=family,
        explicit=explicit,
        behavioral_obligations=behavioral_obligations,
    )
    initial_questions = normalize_questions(analysis.clarification_questions, family=family, shapes=shapes)
    grounded_questions = filter_unsupported_questions(
        initial_questions,
        family=family,
        shapes=shapes,
        explicit=explicit,
        derived_facts=derived_facts,
        behavioral_obligations=behavioral_obligations,
    )
    normalized_questions = filter_resolved_questions(
        grounded_questions,
        derived_facts=derived_facts,
        shapes=shapes,
        family=family,
        behavioral_obligations=behavioral_obligations,
    )
    deterministic_resolution_applied = (
        len(initial_missing) != len(normalized_missing)
        or len(initial_questions) != len(grounded_questions)
        or len(grounded_questions) != len(normalized_questions)
    )

    def _question_resolution_tokens(
        questions: list[ClarificationQuestion],
    ) -> list[str]:
        return [
            (
                canonical_semantic_identity(
                    question.semantic_key,
                    family,
                    question.question,
                )
                or question.semantic_key
                or question.question
            )
            for question in questions
        ]

    explicit_resolution_applied = any(
        key in explicit_keys or key in NONCRITICAL_AMBIGUITY_IDS
        for key in initial_missing
    ) or any(
        token in explicit_keys or token in NONCRITICAL_AMBIGUITY_IDS
        for token in _question_resolution_tokens(initial_questions)
    )

    if explicit_resolution_applied:
        deterministic_resolution_applied = True

    for question in normalized_questions:
        normalized_missing.append(canonical_semantic_identity(question.semantic_key or question.id, family=family, shapes=shapes))

    normalized_missing = [
        item for item in dict.fromkeys(normalized_missing) if item not in explicit_keys and item not in NONCRITICAL_AMBIGUITY_IDS
    ]

    normalized_questions = [
        question for question in dedupe_questions(normalized_questions)
        if canonical_semantic_identity(question.semantic_key or question.id, family=family, shapes=shapes) not in explicit_keys
        and question.id not in NONCRITICAL_AMBIGUITY_IDS
    ]

    if not analysis.ready and not deterministic_resolution_applied and not normalized_missing and not normalized_questions:
        fallback_missing = [
            item
            for item in filter_resolved_labels(
                sanitize_reason_labels([*analysis.missing_critical, *analysis.ambiguous], family=family),
                derived_facts=derived_facts,
                shapes=shapes,
                family=family,
                explicit=explicit,
                behavioral_obligations=behavioral_obligations,
            )
            if item not in explicit_keys and item not in NONCRITICAL_AMBIGUITY_IDS
        ]
        fallback_questions = [
            question
            for question in dedupe_questions(
                filter_resolved_questions(
                    filter_unsupported_questions(
                        normalize_generic_questions(analysis.clarification_questions, family=family, shapes=shapes),
                        family=family,
                        shapes=shapes,
                        explicit=explicit,
                        derived_facts=derived_facts,
                        behavioral_obligations=behavioral_obligations,
                    ),
                    derived_facts=derived_facts,
                    shapes=shapes,
                    family=family,
                    behavioral_obligations=behavioral_obligations,
                )
            )
            if canonical_semantic_identity(question.semantic_key or question.id, family=family, shapes=shapes) not in explicit_keys
            and question.id not in NONCRITICAL_AMBIGUITY_IDS
        ]
        normalized_missing = fallback_missing
        normalized_questions = fallback_questions

    final_missing = list(dict.fromkeys(normalized_missing))
    final_questions = dedupe_questions(normalized_questions)
    final_ambiguous = final_missing
    no_unresolved_evidence = not final_missing and not final_questions and not final_ambiguous
    if no_unresolved_evidence:
        if not analysis.ready and not deterministic_resolution_applied:
            raise AmbiguityPolicyInconsistencyError(
                "Requirement ambiguity normalization lost every not-ready reason without any deterministic resolution or grounded filtering."
            )
        ready = True
    else:
        ready = False

    return RequirementAnalysis(
        ready=ready,
        explicitly_specified=analysis.explicitly_specified,
        safely_inferred=analysis.safely_inferred,
        missing_critical=final_missing,
        ambiguous=final_ambiguous,
        clarification_questions=final_questions,
        assumptions=analysis.assumptions,
        behavioral_obligations=behavioral_obligations,
    )


def finalize_requirement_analysis_state(analysis: RequirementAnalysis) -> RequirementAnalysis:
    """Recompute final readiness from the post-normalization ambiguity state before result construction."""

    final_questions = dedupe_questions(list(analysis.clarification_questions))
    final_unresolved = list(dict.fromkeys([*analysis.missing_critical, *analysis.ambiguous]))

    if final_questions:
        return RequirementAnalysis(
            ready=False,
            explicitly_specified=analysis.explicitly_specified,
            safely_inferred=analysis.safely_inferred,
            missing_critical=final_unresolved,
            ambiguous=final_unresolved,
            clarification_questions=final_questions,
            assumptions=analysis.assumptions,
            behavioral_obligations=analysis.behavioral_obligations,
        )

    if final_unresolved:
        if analysis.ready:
            raise AmbiguityPolicyInconsistencyError(
                "Requirement ambiguity analysis reached ready=True while unresolved ambiguity labels still remained."
            )
        raise AmbiguityPolicyInconsistencyError(
            "Requirement ambiguity analysis retained unresolved ambiguity labels after deterministic filtering, but no clarification questions remained to ask the user."
        )

    return RequirementAnalysis(
        ready=True,
        explicitly_specified=analysis.explicitly_specified,
        safely_inferred=analysis.safely_inferred,
        missing_critical=[],
        ambiguous=[],
        clarification_questions=[],
        assumptions=analysis.assumptions,
        behavioral_obligations=analysis.behavioral_obligations,
    )


def normalize_labels(labels: list[str], family: str | None) -> list[str]:
    """Normalize free-form ambiguity labels into canonical ids."""

    normalized: list[str] = []
    for label in labels:
        if is_implementation_detail_semantic_key(label, family):
            continue
        canonical = normalize_semantic_key(label, family=family) or canonicalize_ambiguity(label, family=family)
        if canonical is not None:
            normalized.append(canonical)
    return list(dict.fromkeys(normalized))


def sanitize_reason_labels(labels: list[str], family: str | None) -> list[str]:
    """Preserve non-empty machine-readable ambiguity reason labels when canonicalization is unavailable."""

    sanitized: list[str] = []
    for label in labels:
        stripped = label.strip()
        if is_incompatible_family_artifact(stripped, family=family):
            continue
        if stripped:
            sanitized.append(stripped)
    return list(dict.fromkeys(sanitized))


def derive_requirement_facts(requirement: str) -> dict[str, DerivedFact]:
    """Derive narrow, deterministic requirement facts before asking clarification questions."""

    text = requirement.lower()
    derived: dict[str, DerivedFact] = {}
    bit_widths = extract_bit_width_values(text)
    shapes = detect_requirement_shapes(text)
    operation_tokens = extract_explicit_operation_tokens(text)

    if operation_tokens:
        derived["operations"] = DerivedFact(
            key="operations",
            value=",".join(sorted(operation_tokens)),
            source="EXPLICIT_REQUIREMENT",
            reason="Requirement explicitly enumerates executable operations.",
        )

    signedness_relevant = operations_require_signedness_clarification(text, operation_tokens)
    if operation_tokens and not signedness_relevant and operation_tokens.issubset(SIGNEDNESS_INSENSITIVE_OPERATION_TOKENS):
        derived["signedness_irrelevant"] = DerivedFact(
            key="signedness_irrelevant",
            value=True,
            source="POLICY_DERIVATION",
            reason="The explicitly requested operations use same-width bit-vector semantics that do not depend on signedness.",
        )
    elif operation_tokens and signedness_relevant:
        derived["signedness_relevant"] = DerivedFact(
            key="signedness_relevant",
            value=True,
            source="POLICY_DERIVATION",
            reason="At least one explicitly requested operation has behavior that can change under signed versus unsigned interpretation.",
        )

    if "encoder_like" in shapes and len(bit_widths) == 1:
        input_count = bit_widths[0]
        if input_count > 0:
            derived["input_width"] = DerivedFact(
                key="input_width",
                value=input_count,
                source="EXPLICIT_REQUIREMENT",
                reason=f"Requirement explicitly states {input_count}-bit encoder input width.",
            )
            derived["input_count"] = DerivedFact(
                key="input_count",
                value=input_count,
                source="EXPLICIT_REQUIREMENT",
                reason=f"Requirement explicitly states an {input_count}-bit encoder, giving {input_count} input positions.",
            )
            derived["input_representation"] = DerivedFact(
                key="input_representation",
                value="bit_vector",
                source="POLICY_DERIVATION",
                reason="Encoder-like wording with explicit bit-vector width implies a request/input bit vector rather than an encoded index input.",
            )
            if input_count > 1:
                output_width = math.ceil(math.log2(input_count))
                derived["encoded_output_width"] = DerivedFact(
                    key="encoded_output_width",
                    value=output_width,
                    source="MATHEMATICAL_DERIVATION",
                    reason=f"Encoded output width is ceil(log2({input_count})) = {output_width}.",
                )

    return derived


def filter_resolved_labels(
    labels: list[str],
    derived_facts: dict[str, DerivedFact],
    shapes: set[str],
    family: str | None = None,
    explicit: set[str] | None = None,
    behavioral_obligations: list[BehavioralObligation] | None = None,
) -> list[str]:
    """Remove unresolved labels that are already covered or semantically inapplicable."""

    if explicit is None:
        explicit = set()
    if behavioral_obligations is None:
        behavioral_obligations = []
    filtered: list[str] = []
    for label in labels:
        canonical_label = normalize_semantic_key(label, family=family, shapes=shapes) or canonical_semantic_identity(
            label,
            family=family,
            shapes=shapes,
        )
        behavior_target = behavior_target_from_semantic_key(canonical_label)
        if behavior_target is not None and any(
            obligation.complete and obligation.target.casefold() == behavior_target
            for obligation in behavioral_obligations
        ):
            continue
        if normalize_semantic_key(label, family=family, shapes=shapes) is not None and not is_semantic_key_applicable(
            canonical_label,
            family=family,
            shapes=shapes,
            explicit=explicit,
            derived_facts=derived_facts,
            behavioral_obligations=behavioral_obligations,
        ):
            continue
        resolution_keys = infer_resolution_keys_from_label(label, shapes=shapes)
        if resolution_keys and all(key in derived_facts for key in resolution_keys):
            continue
        filtered.append(canonical_label)
    return list(dict.fromkeys(filtered))


def filter_resolved_questions(
    questions: list[ClarificationQuestion],
    derived_facts: dict[str, DerivedFact],
    shapes: set[str],
    family: str | None,
    behavioral_obligations: list[BehavioralObligation],
) -> list[ClarificationQuestion]:
    """Drop clarification questions whose requested fact is already deterministically resolved."""

    filtered: list[ClarificationQuestion] = []
    for question in questions:
        if is_implementation_detail_question(question, family):
            continue
        behavior_target = behavior_target_from_semantic_key(question.semantic_key or question.id)
        if behavior_target is not None and any(
            obligation.complete and obligation.target.casefold() == behavior_target
            for obligation in behavioral_obligations
        ):
            continue
        resolution_keys = infer_resolution_keys_from_question(question, shapes=shapes)
        if resolution_keys and all(key in derived_facts for key in resolution_keys):
            continue
        filtered.append(question)
    return filtered


def filter_unsupported_questions(
    questions: list[ClarificationQuestion],
    family: str | None,
    shapes: set[str],
    explicit: set[str],
    derived_facts: dict[str, DerivedFact],
    behavioral_obligations: list[BehavioralObligation],
) -> list[ClarificationQuestion]:
    """Drop clarification questions whose structured concept is incompatible with the detected requirement context."""

    filtered: list[ClarificationQuestion] = []
    for question in questions:
        semantic_key = question.semantic_key
        if semantic_key is None:
            filtered.append(question)
            continue
        if not is_semantic_key_applicable(
            semantic_key,
            family=family,
            shapes=shapes,
            explicit=explicit,
            derived_facts=derived_facts,
            behavioral_obligations=behavioral_obligations,
        ):
            continue
        filtered.append(question)
    return filtered


def is_semantic_key_applicable(
    semantic_key: str,
    *,
    family: str | None,
    shapes: set[str],
    explicit: set[str],
    derived_facts: dict[str, DerivedFact],
    behavioral_obligations: list[BehavioralObligation] | None = None,
) -> bool:
    """Return True only when one clarification semantic concept is grounded in the current requirement context."""

    canonical_key = canonical_semantic_identity(semantic_key, family=family, shapes=shapes)
    explicit_keys = normalize_explicit_semantic_keys(explicit, family=family, shapes=shapes)
    if behavioral_obligations is None:
        behavioral_obligations = []

    behavior_target = behavior_target_from_semantic_key(canonical_key)
    if behavior_target is not None and any(
        obligation.target.casefold() == behavior_target
        for obligation in behavioral_obligations
    ):
        return True

    if canonical_key in {"input_width", "input_count", "output_width", "encoded_output_width", "input_representation"}:
        return True

    if canonical_key in {"select_mapping"}:
        return family == FAMILY_MUX

    if canonical_key == "signedness":
        if "signedness_irrelevant" in derived_facts:
            return False
        if "signedness_relevant" in derived_facts:
            return True
        return family == FAMILY_ALU or canonical_key in explicit_keys or canonical_key in derived_facts

    if canonical_key in {"opcode_mapping", "carry_behavior"}:
        return (
            family == FAMILY_ALU
            or "selector_dispatch_like" in shapes
            or canonical_key in explicit_keys
            or canonical_key in derived_facts
        )

    if canonical_key in {"overflow_behavior", "count_direction", "enable_behavior", "state_width"}:
        return family == FAMILY_COUNTER or canonical_key in explicit_keys or canonical_key in derived_facts

    if canonical_key in {"reset_presence", "reset_type", "reset_polarity", "reset_value", "clock_edge"}:
        return family == FAMILY_COUNTER or canonical_key in explicit_keys or canonical_key in derived_facts

    if canonical_key in {"priority_direction"}:
        return "priority_encoder_like" in shapes or canonical_key in explicit_keys or canonical_key in derived_facts

    if canonical_key in {"valid_output_presence", "no_active_input_behavior"}:
        return "encoder_like" in shapes or canonical_key in explicit_keys or canonical_key in derived_facts

    if canonical_key in {"latency"}:
        return canonical_key in explicit_keys or canonical_key in derived_facts

    if canonical_key in {"operations"}:
        return family == FAMILY_ALU or canonical_key in explicit_keys or canonical_key in derived_facts

    return canonical_key in explicit_keys or canonical_key in derived_facts


def normalize_questions(
    questions: list[ClarificationQuestion],
    family: str | None,
    shapes: set[str],
) -> list[ClarificationQuestion]:
    """Normalize clarification questions into canonical semantic concepts."""

    normalized: list[ClarificationQuestion] = []
    for question in questions:
        canonical_id = canonicalize_ambiguity(" ".join([question.id, question.field]), family=family)
        semantic_key = normalize_semantic_key(question.semantic_key, family=family, shapes=shapes)
        if semantic_key is None and canonical_id is not None:
            semantic_key = semantic_key_for_canonical_id(canonical_id, shapes=shapes)
        if canonical_id is None and semantic_key is None:
            continue
        if canonical_id in NONCRITICAL_AMBIGUITY_IDS:
            continue
        normalized.append(
            ClarificationQuestion(
                id=canonical_id or question.id.strip(),
                field=canonical_field(family, canonical_id) if canonical_id is not None else question.field.strip(),
                semantic_key=semantic_key,
                question=question.question.strip(),
                reason=question.reason.strip(),
                required=question.required,
                choices=question.choices,
                default=question.default,
            )
        )
    return normalized


def normalize_generic_questions(
    questions: list[ClarificationQuestion],
    family: str | None,
    shapes: set[str],
) -> list[ClarificationQuestion]:
    """Preserve non-family-specific questions for unsupported families without leaking wrong template ids."""

    normalized: list[ClarificationQuestion] = []
    generic_index = 1
    for question in questions:
        semantic_key = (
            normalize_semantic_key(question.semantic_key, family=family, shapes=shapes)
            or normalize_semantic_key(question.id, family=family, shapes=shapes)
            or normalize_semantic_key(question.field, family=family, shapes=shapes)
        )
        if is_incompatible_family_artifact(question.id, family=family):
            question_id = f"generic_clarification_{generic_index}"
            generic_index += 1
        else:
            question_id = question.id.strip()

        field = question.field.strip()
        if is_incompatible_family_artifact(field, family=family):
            field = question_id

        normalized.append(
            ClarificationQuestion(
                id=question_id,
                field=field,
                semantic_key=semantic_key,
                question=question.question.strip(),
                reason=question.reason.strip(),
                required=question.required,
                choices=question.choices,
                default=question.default,
            )
        )
    return normalized


BIT_WIDTH_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "eight": 8,
    "sixteen": 16,
    "thirty two": 32,
    "thirty-two": 32,
}


def extract_bit_width_values(text: str) -> list[int]:
    """Extract explicit bit-width values from natural-language requirement text."""

    matches = re.findall(
        r"\b(?P<value>one|two|three|four|eight|sixteen|thirty(?:[- ]two)?|\d+)\s*-\s*bit\b"
        r"|\b(?P<value_spaced>one|two|three|four|eight|sixteen|thirty(?:[- ]two)?|\d+)\s+bit\b",
        text,
    )

    widths: list[int] = []
    for hyphenated_value, spaced_value in matches:
        raw_value = hyphenated_value or spaced_value
        normalized_value = raw_value.lower().strip()
        if normalized_value.isdigit():
            widths.append(int(normalized_value))
            continue
        mapped = BIT_WIDTH_WORDS.get(normalized_value)
        if mapped is not None:
            widths.append(mapped)
    return widths


def detect_requirement_shapes(text: str) -> set[str]:
    """Detect narrow generic design-shape cues used for safe derivations."""

    shapes: set[str] = set()
    if re.search(r"\b(?:priority\s+)?encoder\b", text):
        shapes.add("encoder_like")
    if re.search(r"\bpriority\s+encoder\b", text):
        shapes.add("priority_encoder_like")
    if has_opcode_mapping(text):
        shapes.add("selector_dispatch_like")
    return shapes


def infer_resolution_keys_from_question(question: ClarificationQuestion, shapes: set[str]) -> set[str]:
    """Infer which deterministic fact keys would resolve a clarification question."""

    if question.semantic_key is not None:
        return semantic_key_to_resolution_keys(question.semantic_key, shapes=shapes)
    structured_key = normalize_semantic_key(question.id, shapes=shapes) or normalize_semantic_key(question.field, shapes=shapes)
    if structured_key is not None:
        return semantic_key_to_resolution_keys(structured_key, shapes=shapes)
    return set()


def semantic_key_to_resolution_keys(semantic_key: str, shapes: set[str]) -> set[str]:
    """Map one semantic clarification key to the deterministic fact keys that resolve it."""

    canonical_key = canonical_semantic_identity(semantic_key, shapes=shapes)
    if canonical_key in {
        "input_width",
        "input_count",
        "output_width",
        "encoded_output_width",
        "input_representation",
        "operations",
    }:
        return {canonical_key}
    return set()


def normalize_explicit_semantic_keys(
    explicit: set[str],
    *,
    family: str | None,
    shapes: set[str],
) -> set[str]:
    """Normalize explicit machine-readable facts into the same semantic-key space used by filtering."""

    keys: set[str] = set()
    for item in explicit:
        semantic_key = normalize_semantic_key(item, family=family, shapes=shapes)
        if semantic_key is not None:
            keys.add(semantic_key)
            continue
        stripped = item.strip()
        if stripped:
            keys.add(canonical_semantic_identity(stripped, family=family, shapes=shapes))
    return keys


def normalize_semantic_key(raw_key: str | None, family: str | None = None, shapes: set[str] | None = None) -> str | None:
    """Normalize structured clarification semantics without relying on free-form question prose."""

    if raw_key is None:
        return None
    if shapes is None:
        shapes = set()
    normalized = " ".join(raw_key.lower().replace(".", " ").replace("_", " ").split())
    artifact = identify_family_specific_artifact(raw_key)
    if artifact is not None:
        _, canonical_id = artifact
        return semantic_key_for_canonical_id(canonical_id, shapes=shapes)
    canonical = SEMANTIC_KEY_ALIASES.get(normalized.replace(" ", "_"))
    if canonical is not None:
        return canonical_semantic_identity(canonical, family=family, shapes=shapes)
    normalized_key = normalized.replace(" ", "_")
    if normalized_key in GENERIC_STRUCTURAL_SEMANTIC_KEYS or behavior_target_from_semantic_key(normalized_key) is not None:
        return canonical_semantic_identity(normalized_key, family=family, shapes=shapes)
    return None


def semantic_key_for_canonical_id(canonical_id: str, shapes: set[str] | None = None) -> str | None:
    """Map a canonical family-specific ambiguity id to one generic semantic key."""

    alias = SEMANTIC_KEY_ALIASES.get(canonical_id)
    if alias is None:
        return None
    return canonical_semantic_identity(alias, shapes=shapes)


def canonical_semantic_identity(raw_key: str, family: str | None = None, shapes: set[str] | None = None) -> str:
    """Collapse semantically equivalent structured keys into one canonical identity for the current context."""

    if shapes is None:
        shapes = set()
    normalized = raw_key.strip()
    if not normalized:
        return normalized
    key = normalized.lower().replace(".", "_").replace(" ", "_")
    if key == "output_width" and "encoder_like" in shapes:
        return "encoded_output_width"
    return key


def question_identity(question: ClarificationQuestion) -> str:
    """Return the stable semantic identity for one clarification question."""

    return question.semantic_key or question.id


def infer_resolution_keys_from_label(label: str, shapes: set[str]) -> set[str]:
    """Infer deterministic fact keys from machine-readable unresolved labels before falling back to legacy text rules."""

    structured_key = normalize_semantic_key(label, shapes=shapes)
    if structured_key is not None:
        return semantic_key_to_resolution_keys(structured_key, shapes=shapes)
    return infer_resolution_keys_from_text(label)


def infer_resolution_keys_from_text(text: str) -> set[str]:
    """Infer which deterministic fact keys correspond to a question or unresolved label."""

    normalized = " ".join(text.lower().replace("_", " ").replace(".", " ").split())
    resolution_keys: set[str] = set()

    if any(phrase in normalized for phrase in ["how many inputs", "number of inputs", "input count", "number of choices"]):
        resolution_keys.add("input_count")
    if any(
        phrase in normalized
        for phrase in [
            "input width",
            "width of input",
            "width of the input",
            "data bus width",
            "width of the data bus",
            "input vector width",
        ]
    ):
        resolution_keys.add("input_width")
    if any(
        phrase in normalized
        for phrase in [
            "output width",
            "encoded output width",
            "index width",
            "output bits",
            "how many output bits",
        ]
    ):
        resolution_keys.add("encoded_output_width")
    if any(
        phrase in normalized
        for phrase in [
            "binary or one-hot input",
            "one-hot input",
            "binary input",
            "input representation",
        ]
    ):
        resolution_keys.add("input_representation")

    if "mux input count" in normalized:
        resolution_keys.add("input_count")
    if "mux data width" in normalized:
        resolution_keys.add("input_width")
    if any(
        phrase in normalized
        for phrase in [
            "supported operations",
            "arithmetic operations",
            "which operations",
            "operation set",
            "behavior operations",
        ]
    ):
        resolution_keys.add("operations")
    return resolution_keys


def canonicalize_ambiguity(label: str, family: str | None) -> str | None:
    """Map a raw ambiguity label to a canonical semantic concept."""

    normalized = " ".join(label.lower().replace(".", " ").replace("_", " ").split())

    if "signed" in normalized:
        return "signedness"
    if "operation" in normalized:
        return "operations"

    if family in CANONICAL_ALIASES_BY_FAMILY:
        for canonical_id, aliases in CANONICAL_ALIASES_BY_FAMILY[family].items():
            if normalized == canonical_id.replace("_", " "):
                return canonical_id
            if normalized in aliases:
                return canonical_id
        if family == FAMILY_COUNTER and "signed" in normalized:
            return None
        if family == FAMILY_ALU:
            if "width" in normalized and "opcode" not in normalized:
                return "alu_width"
            if "operation" in normalized:
                return "alu_operations"
            if "signed" in normalized:
                return "alu_signedness"
            if "opcode" in normalized or "control" in normalized:
                return "opcode_mapping"
        if family == FAMILY_COUNTER:
            if "width" in normalized:
                return "counter_width"
            if "clock edge" in normalized or normalized == "edge":
                return "clock_edge"
            if "reset" in normalized and "presence" in normalized:
                return "reset_presence"
            if "reset type" in normalized:
                return "reset_type"
            if "reset polarity" in normalized or "active high" in normalized or "active low" in normalized:
                return "reset_polarity"
            if "direction" in normalized:
                return "count_direction"
            if "overflow" in normalized or "wrap" in normalized:
                return "overflow_behavior"
        if family == FAMILY_MUX:
            if "width" in normalized:
                return "mux_data_width"
            if "input" in normalized and "count" in normalized:
                return "mux_input_count"
            if "select" in normalized:
                return "mux_select_mapping"

    return None


def identify_family_specific_artifact(label: str) -> tuple[str, str] | None:
    """Identify whether one label is a known family-specific canonical ambiguity artifact."""

    normalized = " ".join(label.lower().replace(".", " ").replace("_", " ").split())
    for candidate_family, aliases_by_id in CANONICAL_ALIASES_BY_FAMILY.items():
        for canonical_id, aliases in aliases_by_id.items():
            if normalized == canonical_id.replace("_", " "):
                return candidate_family, canonical_id
            if normalized in aliases:
                return candidate_family, canonical_id
    return None


def is_incompatible_family_artifact(label: str, family: str | None) -> bool:
    """Return True when one known family-specific ambiguity artifact does not belong to the detected family."""

    identified = identify_family_specific_artifact(label)
    if identified is None:
        return False
    artifact_family, _ = identified
    if family is None:
        return True
    return artifact_family != family


def make_canonical_question(family: str, canonical_id: str) -> ClarificationQuestion:
    """Construct a canonical clarification question for a known family."""

    payload = CANONICAL_QUESTIONS_BY_FAMILY[family][canonical_id]
    return ClarificationQuestion(
        id=canonical_id,
        field=str(payload["field"]),
        semantic_key=semantic_key_for_canonical_id(canonical_id),
        question=str(payload["question"]),
        reason=str(payload["reason"]),
        required=True,
        choices=list(payload["choices"]),
        default=None,
    )


def canonical_field(family: str | None, canonical_id: str) -> str:
    """Return the canonical field path for a canonical ambiguity id."""

    if family in CANONICAL_QUESTIONS_BY_FAMILY and canonical_id in CANONICAL_QUESTIONS_BY_FAMILY[family]:
        return str(CANONICAL_QUESTIONS_BY_FAMILY[family][canonical_id]["field"])
    return canonical_id


def merge_questions(
    existing: ClarificationQuestion,
    new: ClarificationQuestion,
    prefer_new: bool = False,
) -> ClarificationQuestion:
    """Merge two questions about the same canonical ambiguity."""

    chosen_question = new.question if prefer_new else existing.question
    chosen_field = new.field if prefer_new else existing.field
    chosen_reason = new.reason if len(new.reason) > len(existing.reason) else existing.reason
    if prefer_new and new.reason:
        chosen_reason = new.reason if len(new.reason) >= len(existing.reason) else existing.reason
    merged_choices = list(dict.fromkeys([*existing.choices, *new.choices]))
    default = existing.default if existing.default is not None else new.default

    return ClarificationQuestion(
        id=existing.id,
        field=chosen_field,
        semantic_key=existing.semantic_key or new.semantic_key,
        question=chosen_question,
        reason=chosen_reason,
        required=existing.required or new.required,
        choices=merged_choices,
        default=default,
    )


def dedupe_questions(questions: list[ClarificationQuestion]) -> list[ClarificationQuestion]:
    """Deduplicate clarification questions by semantic identity when available."""

    merged: dict[str, ClarificationQuestion] = {}
    for question in questions:
        identity = question_identity(question)
        if identity in merged:
            merged[identity] = merge_questions(merged[identity], question, prefer_new=False)
        else:
            merged[identity] = question
    return list(merged.values())


def has_any_bit_width(text: str) -> bool:
    return re.search(
        r"\b(?:one|two|three|four|eight|sixteen|thirty[- ]two|\d+)\s*-\s*bit\b"
        r"|\b(?:one|two|three|four|eight|sixteen|thirty[- ]two|\d+)\s+bit\b",
        text,
    ) is not None


def has_clock_edge(text: str) -> bool:
    return re.search(r"\bpositive-edge\b|\bnegative-edge\b|\brising edge\b|\bfalling edge\b|\bposedge\b|\bnegedge\b", text) is not None


def text_mentions_reset(text: str) -> bool:
    return re.search(r"\breset\b|\brst\b", text) is not None


def has_reset_type(text: str) -> bool:
    return "synchronous reset" in text or "asynchronous reset" in text


def has_reset_polarity(text: str) -> bool:
    return "active-high" in text or "active-low" in text or "active high" in text or "active low" in text


def has_counter_direction(text: str) -> bool:
    return re.search(r"\bup-counter\b|\bdown-counter\b|\bcount up\b|\bcount down\b|\bup-counter\b|\bup counter\b|\bdown counter\b|\bbidirectional\b|\bup/down\b", text) is not None


def has_overflow_behavior(text: str) -> bool:
    return re.search(r"\bwrap\b|\bwraparound\b|\bsaturat|\boverflow\b", text) is not None


def has_reset_value(text: str) -> bool:
    return re.search(r"\bclear(?:s)?\b.*\bzero\b|\breset\b.*\bzero\b|\breset to\b", text) is not None


def has_operations(text: str) -> bool:
    return re.search(r"\badd\b|\bsub\b|\band\b|\bor\b|\bxor\b|\bshift\b|\bcompare\b", text) is not None


def has_multiple_operations(text: str) -> bool:
    matches = re.findall(r"\badd\b|\bsub\b|\band\b|\bor\b|\bxor\b|\bshift\b|\bcompare\b", text)
    return len(set(matches)) > 1


def has_signedness(text: str) -> bool:
    return re.search(r"\bsigned\b|\bunsigned\b", text) is not None


def has_opcode_mapping(text: str) -> bool:
    if "opcode" in text:
        return True
    patterns = [
        r"\b(?:when\s+)?(?:op|opcode|mode|select|selector|sel|case)\s*(?:is|=)?\s*\d+\b",
        r"\b(?:op|opcode|mode|select|selector|sel)\s+\d+\s+(?:selects|performs|returns|outputs)\b",
        r"\b\d+\s*(?:->|:)\s*(?:add|sub|subtract|xor|and|or|shift|compare|output|return)\b",
    ]
    return any(re.search(pattern, text) is not None for pattern in patterns)


def has_mux_input_count(text: str) -> bool:
    return re.search(r"\b2-to-1\b|\b4-to-1\b|\b8-to-1\b|\btwo-to-one\b|\bthree-to-one\b|\bone-bit inputs a and b\b", text) is not None


def has_select_mapping(text: str) -> bool:
    return "when select" in text or "otherwise" in text or "select is 0" in text or "select input" in text


def extract_explicit_operation_tokens(text: str) -> set[str]:
    """Extract a narrow set of explicitly requested operation semantics from requirement text."""

    operations: set[str] = set()
    if re.search(r"\badd(?:ition)?\b|\bplus\b|\bsum\b", text):
        operations.add("ADD")
    if re.search(r"\bsub(?:tract|traction)?\b|\bminus\b|\bdifference\b", text):
        operations.add("SUB")
    if re.search(r"\bxor\b|\bexclusive or\b", text):
        operations.add("BIT_XOR")
    if re.search(r"\bbitwise and\b|\blogical and\b|&", text):
        operations.add("BIT_AND")
    if re.search(r"\bbitwise or\b|\blogical or\b|\|", text):
        operations.add("BIT_OR")
    if re.search(r"\bnot equal\b|\b!=\b", text):
        operations.add("NE")
    if re.search(r"\b==\b|\bequality\b", text):
        operations.add("EQ")
    operations.update(extract_explicit_comparison_tokens(text))
    if re.search(r"\barithmetic right shift\b", text):
        operations.add("ARITH_SHIFT_RIGHT")
    return operations


def extract_explicit_comparison_tokens(text: str) -> set[str]:
    """Extract unambiguous comparison operators from natural-language identifier-to-identifier comparisons."""

    operations: set[str] = set()
    if re.search(r"\b[A-Za-z_][A-Za-z0-9_$]*\b\s+(?:is\s+)?greater than or equal to\s+\b[A-Za-z_][A-Za-z0-9_$]*\b", text):
        operations.add("GE")
    elif re.search(r"\b[A-Za-z_][A-Za-z0-9_$]*\b\s+(?:is\s+)?greater than\s+\b[A-Za-z_][A-Za-z0-9_$]*\b", text):
        operations.add("GT")

    if re.search(r"\b[A-Za-z_][A-Za-z0-9_$]*\b\s+(?:is\s+)?less than or equal to\s+\b[A-Za-z_][A-Za-z0-9_$]*\b", text):
        operations.add("LE")
    elif re.search(r"\b[A-Za-z_][A-Za-z0-9_$]*\b\s+(?:is\s+)?less than\s+\b[A-Za-z_][A-Za-z0-9_$]*\b", text):
        operations.add("LT")

    if re.search(r"\b[A-Za-z_][A-Za-z0-9_$]*\b\s+(?:is\s+)?not equal to\s+\b[A-Za-z_][A-Za-z0-9_$]*\b", text):
        operations.add("NE")
    elif re.search(r"\b[A-Za-z_][A-Za-z0-9_$]*\b\s+(?:is\s+)?equal to\s+\b[A-Za-z_][A-Za-z0-9_$]*\b", text):
        operations.add("EQ")

    return operations


def build_signedness_clarification_question(requirement: str) -> ClarificationQuestion:
    """Build one generic signedness clarification question scoped to sign-sensitive comparison semantics."""

    question_text = "Should comparisons use signed or unsigned interpretation?"
    comparison_signals = extract_comparison_signal_pair(requirement.lower())
    if comparison_signals is not None:
        left_signal, right_signal = comparison_signals
        question_text = f"Should comparisons between {left_signal} and {right_signal} use signed or unsigned interpretation?"

    return ClarificationQuestion(
        id="signedness",
        field="ports.signed",
        semantic_key="signedness",
        question=question_text,
        reason="Ordered comparisons such as greater-than or less-than can change behavior under signed versus unsigned interpretation.",
        required=True,
        choices=["signed", "unsigned"],
        default=None,
    )


def extract_comparison_signal_pair(text: str) -> tuple[str, str] | None:
    """Extract one obvious identifier pair from a natural-language comparison phrase when available."""

    patterns = [
        r"\b(?P<left>[A-Za-z_][A-Za-z0-9_$]*)\b\s+(?:is\s+)?greater than or equal to\s+\b(?P<right>[A-Za-z_][A-Za-z0-9_$]*)\b",
        r"\b(?P<left>[A-Za-z_][A-Za-z0-9_$]*)\b\s+(?:is\s+)?greater than\s+\b(?P<right>[A-Za-z_][A-Za-z0-9_$]*)\b",
        r"\b(?P<left>[A-Za-z_][A-Za-z0-9_$]*)\b\s+(?:is\s+)?less than or equal to\s+\b(?P<right>[A-Za-z_][A-Za-z0-9_$]*)\b",
        r"\b(?P<left>[A-Za-z_][A-Za-z0-9_$]*)\b\s+(?:is\s+)?less than\s+\b(?P<right>[A-Za-z_][A-Za-z0-9_$]*)\b",
        r"\b(?P<left>[A-Za-z_][A-Za-z0-9_$]*)\b\s+(?:is\s+)?not equal to\s+\b(?P<right>[A-Za-z_][A-Za-z0-9_$]*)\b",
        r"\b(?P<left>[A-Za-z_][A-Za-z0-9_$]*)\b\s+(?:is\s+)?equal to\s+\b(?P<right>[A-Za-z_][A-Za-z0-9_$]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match is not None:
            return match.group("left"), match.group("right")
    return None


def operations_require_signedness_clarification(text: str, operation_tokens: set[str]) -> bool:
    """Return True only when signedness can change the executable behavior of explicit operations."""

    if not operation_tokens:
        return False
    if operation_tokens & SIGNEDNESS_SENSITIVE_OPERATION_TOKENS:
        return True
    if re.search(r"\bsign extend\b|\bsigned compare\b|\bunsigned compare\b|\bsaturat|\boverflow flag\b", text):
        return True
    return False


def enrich_requirement_for_generation(requirement: str, analysis: RequirementAnalysis) -> str:
    """Augment the generation prompt input with explicit analysis constraints."""

    lines = [requirement.strip(), "", "Requirement analysis constraints:"]
    if analysis.explicitly_specified:
        lines.append("Explicitly specified:")
        for item in analysis.explicitly_specified:
            lines.append(f"- {item}")
    if analysis.safely_inferred:
        lines.append("Safely inferred:")
        for item in analysis.safely_inferred:
            lines.append(f"- {item}")
    if analysis.assumptions:
        lines.append("Allowed noncritical assumptions:")
        for item in analysis.assumptions:
            lines.append(f"- {item}")
    complete_obligations = [
        obligation for obligation in analysis.behavioral_obligations if obligation.complete
    ]
    if complete_obligations:
        lines.extend(
            [
                "",
                "RESOLVED REQUIREMENT FACTS (authoritative):",
                "Preserve every condition and branch exactly in HardwareIntent.",
            ]
        )
        for obligation in complete_obligations:
            if obligation.condition is None:
                behavior = f"target={obligation.target} | value={obligation.when_true}"
            else:
                behavior = (
                    f"target={obligation.target} | condition={obligation.condition} | "
                    f"when_true={obligation.when_true} | when_false={obligation.when_false}"
                )
            lines.append(
                f"- {behavior} | source={obligation.source.value} | evidence={obligation.evidence}"
            )
    lines.append("Do not add unresolved critical behavior.")
    return "\n".join(lines)


def extract_json_object(text: str) -> tuple[dict | None, str | None]:
    """Extract a JSON object from raw LLM text with a minimal defensive strategy."""

    stripped = text.strip()
    if not stripped:
        return None, "Model output was empty."

    try:
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            return None, "Model output must decode to a top-level JSON object."
        return parsed, None
    except json.JSONDecodeError:
        pass

    fenced = strip_single_markdown_fence(stripped)
    if fenced is None:
        return None, "Model output was not valid JSON."

    try:
        parsed = json.loads(fenced)
    except json.JSONDecodeError as exc:
        return None, f"Model output was not valid JSON: {exc}"

    if not isinstance(parsed, dict):
        return None, "Model output must decode to a top-level JSON object."
    return parsed, None


def normalize_analysis_payload(payload: dict) -> dict:
    """Repair small, obvious analysis-payload representation mismatches before validation."""

    normalized = dict(payload)
    raw_questions = normalized.get("clarification_questions")
    if isinstance(raw_questions, list):
        normalized_questions: list[object] = []
        for item in raw_questions:
            if isinstance(item, dict):
                question = dict(item)
                question["choices"] = normalize_choices(question.get("choices"))
                semantic_key = question.get("semantic_key")
                if isinstance(semantic_key, str):
                    stripped_semantic_key = semantic_key.strip()
                    question["semantic_key"] = stripped_semantic_key or None
                else:
                    question["semantic_key"] = None
                normalized_questions.append(question)
            else:
                normalized_questions.append(item)
        normalized["clarification_questions"] = normalized_questions
    return normalized


def normalize_hardware_intent_payload(payload: dict) -> dict:
    """Repair only descriptive HardwareIntent metadata fields before strict typed validation."""

    normalized = dict(payload)
    behavior = normalized.get("behavior")
    if behavior is None:
        normalized["behavior"] = {"description": "High-level behavior metadata omitted."}
    elif isinstance(behavior, str):
        stripped = behavior.strip()
        normalized["behavior"] = {
            "description": stripped or "High-level behavior metadata omitted.",
            "operations": [],
            "rules": [],
            "assumptions": [],
        }
    elif isinstance(behavior, dict):
        normalized_behavior = dict(behavior)
        description = normalized_behavior.get("description")
        if not isinstance(description, str) or not description.strip():
            normalized_behavior["description"] = "High-level behavior metadata omitted."
        for field_name in ("operations", "rules", "assumptions"):
            normalized_behavior[field_name] = normalize_descriptive_string_list(normalized_behavior.get(field_name))
        normalized["behavior"] = normalized_behavior
    else:
        normalized["behavior"] = {
            "description": "High-level behavior metadata omitted.",
            "rules": normalize_descriptive_string_list(behavior),
            "operations": [],
            "assumptions": [],
        }

    for field_name in ("notes", "tags"):
        normalized[field_name] = normalize_descriptive_string_list(normalized.get(field_name))

    return normalized


def validate_hardware_intent_envelope(payload: dict) -> list[str]:
    """Require the authoritative HardwareIntent envelope before strict typed validation."""

    required_fields = [
        "module_name",
        "design_type",
        "ports",
    ]
    missing = [field_name for field_name in required_fields if field_name not in payload]
    if missing:
        return [
            "INVALID_HARDWARE_INTENT_ENVELOPE: Return the complete authoritative HardwareIntent JSON object with "
            f"required fields {', '.join(required_fields)}. Missing: {', '.join(missing)}. "
            f"Present keys: {', '.join(str(key) for key in payload.keys()) or '(none)'}"
        ]

    design_type = payload.get("design_type")
    if isinstance(design_type, str) and design_type.strip().lower() == "combinational" and "combinational_intent" not in payload:
        return [
            "INVALID_HARDWARE_INTENT_ENVELOPE: Combinational HardwareIntent must include combinational_intent in the "
            "top-level object. Return the full object, not a partial patch."
        ]

    return []


def normalize_descriptive_string_list(value: object) -> list[str]:
    """Normalize descriptive prose metadata into a conservative list of plain strings."""

    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if not isinstance(value, list):
        rendered = render_descriptive_metadata_item(value)
        return [rendered] if rendered else []

    normalized: list[str] = []
    for item in value:
        rendered = render_descriptive_metadata_item(item)
        if rendered:
            normalized.append(rendered)
    return normalized


def render_descriptive_metadata_item(item: object) -> str | None:
    """Render one descriptive metadata item into a plain string without changing authoritative intent fields."""

    if item is None:
        return None
    if isinstance(item, str):
        stripped = item.strip()
        return stripped or None
    if isinstance(item, dict):
        for preferred_key in ("text", "description", "reason", "label", "name", "value"):
            preferred_value = item.get(preferred_key)
            if isinstance(preferred_value, str) and preferred_value.strip():
                return preferred_value.strip()
        try:
            return json.dumps(item, sort_keys=True)
        except TypeError:
            return str(item).strip() or None
    rendered = str(item).strip()
    return rendered or None


def detect_semantic_constraint_payload_inconsistency(payload: dict) -> str | None:
    """Catch obvious semantic-constraint/semantics inconsistencies before full HardwareSpec validation."""

    if not isinstance(payload, dict):
        return None

    semantic_constraints = payload.get("semantic_constraints")
    if semantic_constraints is None:
        return None

    semantics = payload.get("semantics")
    if not isinstance(semantics, dict):
        return (
            "semantic_constraints require corresponding structured semantics with compatible combinational assignments. "
            "Either emit valid semantics.combinational.assignments matching the constraints, or omit semantic_constraints."
        )

    combinational = semantics.get("combinational")
    if not isinstance(combinational, dict):
        return (
            "semantic_constraints require corresponding structured semantics with compatible combinational assignments. "
            "Either emit valid semantics.combinational.assignments matching the constraints, or omit semantic_constraints."
        )

    assignments = combinational.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        return (
            "semantic_constraints require corresponding structured semantics with compatible combinational assignments. "
            "Either emit valid semantics.combinational.assignments matching the constraints, or omit semantic_constraints."
        )

    return None


def normalize_choices(value: object) -> object:
    """Normalize simple clarification-choice encodings into a list of strings."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        for separator in (" / ", "/", " | ", "|", ","):
            if separator in stripped:
                parts = [part.strip() for part in stripped.split(separator) if part.strip()]
                if parts:
                    return parts
        return [stripped]
    return value


def strip_single_markdown_fence(text: str) -> str | None:
    """Strip one outer Markdown code fence if the entire response is fenced."""

    lines = text.splitlines()
    if len(lines) < 3:
        return None
    if not lines[0].strip().startswith("```"):
        return None
    if lines[-1].strip() != "```":
        return None
    inner = "\n".join(lines[1:-1]).strip()
    return inner or None


def format_validation_errors(exc: ValidationError) -> list[str]:
    """Render Pydantic validation errors into readable strings."""

    formatted: list[str] = []
    for error in exc.errors():
        location = " -> ".join(str(part) for part in error["loc"]) or "root"
        formatted.append(f"{location}: {error['msg']}")
    return formatted


__all__ = [
    "AIRequirementParser",
    "REQUIREMENT_ANALYSIS_PROMPT_VERSION",
    "REQUIREMENT_PARSER_PROMPT_VERSION",
    "ALLOWED_NONCRITICAL_ASSUMPTIONS",
    "CRITICAL_AMBIGUITY_POLICY",
    "apply_clarifications",
    "derive_local_clarifications",
    "enrich_requirement_for_generation",
    "extract_json_object",
    "format_validation_errors",
    "validate_hardware_intent_envelope",
    "detect_explicit_details",
    "detect_requirement_family",
    "merge_with_local_ambiguity_policy",
    "normalize_analysis_payload",
    "normalize_requirement_analysis",
]
