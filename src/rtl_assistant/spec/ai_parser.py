import json
import re
import time

from pydantic import ValidationError

from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.llm import (
    ClarificationQuestion,
    RequirementAnalysis,
    RequirementParseResult,
    RequirementStatus,
)
from rtl_assistant.spec.prompts import (
    ALLOWED_NONCRITICAL_ASSUMPTIONS,
    CRITICAL_AMBIGUITY_POLICY,
    REQUIREMENT_ANALYSIS_PROMPT_VERSION,
    REQUIREMENT_PARSER_PROMPT_VERSION,
    build_requirement_analysis_prompt,
    build_requirement_analysis_repair_prompt,
    build_requirement_parser_prompt,
    build_requirement_repair_prompt,
)

FAMILY_COUNTER = "counter"
FAMILY_ALU = "alu"
FAMILY_MUX = "mux"

NONCRITICAL_AMBIGUITY_IDS = {"clock_signal", "reset_signal", "module_name"}

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


class AIRequirementParser:
    """Parse natural-language hardware requirements into validated HardwareSpec objects."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def parse(self, requirement: str) -> RequirementParseResult:
        """Convert a natural-language requirement into a validated HardwareSpec."""

        started_at = time.perf_counter()
        analysis_result = self._analyze_requirement(requirement)
        if isinstance(analysis_result, RequirementParseResult):
            analysis_result.duration_ms = int((time.perf_counter() - started_at) * 1000)
            return analysis_result

        analysis, analysis_attempts, analysis_output = analysis_result
        analysis = merge_with_local_ambiguity_policy(requirement, analysis)

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
                duration_ms=int((time.perf_counter() - started_at) * 1000),
            )

        spec_result = self._generate_hardware_spec(requirement, analysis)
        if isinstance(spec_result, RequirementParseResult):
            spec_result.duration_ms = int((time.perf_counter() - started_at) * 1000)
            spec_result.attempts += analysis_attempts
            return spec_result

        hardware_spec, generation_attempts, raw_model_output = spec_result
        return RequirementParseResult(
            requirement=requirement,
            status=RequirementStatus.READY,
            hardware_spec=hardware_spec,
            clarification_questions=[],
            unresolved_fields=[],
            assumptions=list(hardware_spec.behavior.assumptions),
            raw_model_output=raw_model_output,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            attempts=analysis_attempts + generation_attempts,
            validation_errors=[],
            error_type=None,
            error_message=None,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
        )

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

    def _generate_hardware_spec(
        self, requirement: str, analysis: RequirementAnalysis
    ) -> tuple[HardwareSpec, int, str] | RequirementParseResult:
        """Generate and validate the final HardwareSpec only after readiness is confirmed."""

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


def merge_with_local_ambiguity_policy(requirement: str, analysis: RequirementAnalysis) -> RequirementAnalysis:
    """Apply a conservative local ambiguity policy on top of LLM analysis."""

    family = detect_requirement_family(requirement)
    explicit = detect_explicit_details(requirement, family)
    normalized = normalize_requirement_analysis(analysis, family=family, explicit=explicit)
    local_questions = derive_local_clarifications(requirement, family=family, explicit=explicit)

    merged_questions: dict[str, ClarificationQuestion] = {
        question.id: question for question in normalized.clarification_questions
    }
    for question in local_questions:
        if question.id in merged_questions:
            merged_questions[question.id] = merge_questions(merged_questions[question.id], question, prefer_new=True)
        else:
            merged_questions[question.id] = question

    unresolved_ids = list(
        dict.fromkeys(
            [
                *normalized.missing_critical,
                *(question.id for question in merged_questions.values()),
            ]
        )
    )
    unresolved_ids = [item for item in unresolved_ids if item not in explicit and item not in NONCRITICAL_AMBIGUITY_IDS]

    if not unresolved_ids and not merged_questions:
        return RequirementAnalysis(
            ready=True,
            explicitly_specified=list(dict.fromkeys([*normalized.explicitly_specified, *sorted(explicit)])),
            safely_inferred=normalized.safely_inferred,
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=normalized.assumptions,
        )

    return RequirementAnalysis(
        ready=False,
        explicitly_specified=list(dict.fromkeys([*normalized.explicitly_specified, *sorted(explicit)])),
        safely_inferred=normalized.safely_inferred,
        missing_critical=unresolved_ids,
        ambiguous=unresolved_ids,
        clarification_questions=list(merged_questions.values()),
        assumptions=normalized.assumptions,
    )


def derive_local_clarifications(
    requirement: str,
    family: str | None,
    explicit: set[str],
) -> list[ClarificationQuestion]:
    """Derive conservative clarification questions for obviously underspecified prompts."""

    text = requirement.lower()
    questions: list[ClarificationQuestion] = []

    if family == FAMILY_COUNTER:
        if "counter_width" not in explicit:
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
        if "alu_width" not in explicit:
            questions.append(make_canonical_question(FAMILY_ALU, "alu_width"))
        if "alu_operations" not in explicit:
            questions.append(make_canonical_question(FAMILY_ALU, "alu_operations"))
        if "alu_signedness" not in explicit:
            questions.append(make_canonical_question(FAMILY_ALU, "alu_signedness"))
        if has_multiple_operations(text) and "opcode_mapping" not in explicit:
            questions.append(make_canonical_question(FAMILY_ALU, "opcode_mapping"))

    if family == FAMILY_MUX:
        if "mux_input_count" not in explicit:
            questions.append(make_canonical_question(FAMILY_MUX, "mux_input_count"))
        if "mux_data_width" not in explicit:
            questions.append(make_canonical_question(FAMILY_MUX, "mux_data_width"))
        if "mux_select_mapping" not in explicit:
            questions.append(make_canonical_question(FAMILY_MUX, "mux_select_mapping"))

    return dedupe_questions(questions)


def detect_requirement_family(requirement: str) -> str | None:
    """Detect the primary supported module family from the requirement text."""

    text = requirement.lower()
    if "counter" in text:
        return FAMILY_COUNTER
    if "alu" in text:
        return FAMILY_ALU
    if "multiplexer" in text or re.search(r"\bmux\b", text):
        return FAMILY_MUX
    return None


def detect_explicit_details(requirement: str, family: str | None) -> set[str]:
    """Detect explicitly specified critical concepts from the requirement text."""

    text = requirement.lower()
    explicit: set[str] = set()

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

    return explicit


def normalize_requirement_analysis(
    analysis: RequirementAnalysis,
    family: str | None,
    explicit: set[str],
) -> RequirementAnalysis:
    """Normalize LLM-produced ambiguity labels into canonical semantic concepts."""

    normalized_missing = normalize_labels([*analysis.missing_critical, *analysis.ambiguous], family=family)
    normalized_questions = normalize_questions(analysis.clarification_questions, family=family)

    for question in normalized_questions:
        normalized_missing.append(question.id)

    normalized_missing = [
        item for item in dict.fromkeys(normalized_missing) if item not in explicit and item not in NONCRITICAL_AMBIGUITY_IDS
    ]

    normalized_questions = [
        question for question in dedupe_questions(normalized_questions)
        if question.id not in explicit and question.id not in NONCRITICAL_AMBIGUITY_IDS
    ]

    return RequirementAnalysis(
        ready=analysis.ready and not normalized_missing and not normalized_questions,
        explicitly_specified=analysis.explicitly_specified,
        safely_inferred=analysis.safely_inferred,
        missing_critical=normalized_missing,
        ambiguous=normalized_missing,
        clarification_questions=normalized_questions,
        assumptions=analysis.assumptions,
    )


def normalize_labels(labels: list[str], family: str | None) -> list[str]:
    """Normalize free-form ambiguity labels into canonical ids."""

    normalized: list[str] = []
    for label in labels:
        canonical = canonicalize_ambiguity(label, family=family)
        if canonical is not None:
            normalized.append(canonical)
    return list(dict.fromkeys(normalized))


def normalize_questions(questions: list[ClarificationQuestion], family: str | None) -> list[ClarificationQuestion]:
    """Normalize clarification questions into canonical semantic concepts."""

    normalized: list[ClarificationQuestion] = []
    for question in questions:
        canonical_id = canonicalize_ambiguity(" ".join([question.id, question.field, question.question]), family=family)
        if canonical_id is None or canonical_id in NONCRITICAL_AMBIGUITY_IDS:
            continue
        normalized.append(
            ClarificationQuestion(
                id=canonical_id,
                field=canonical_field(family, canonical_id),
                question=question.question.strip(),
                reason=question.reason.strip(),
                required=question.required,
                choices=question.choices,
                default=question.default,
            )
        )
    return normalized


def canonicalize_ambiguity(label: str, family: str | None) -> str | None:
    """Map a raw ambiguity label to a canonical semantic concept."""

    normalized = " ".join(label.lower().replace(".", " ").replace("_", " ").split())

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


def make_canonical_question(family: str, canonical_id: str) -> ClarificationQuestion:
    """Construct a canonical clarification question for a known family."""

    payload = CANONICAL_QUESTIONS_BY_FAMILY[family][canonical_id]
    return ClarificationQuestion(
        id=canonical_id,
        field=str(payload["field"]),
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
        question=chosen_question,
        reason=chosen_reason,
        required=existing.required or new.required,
        choices=merged_choices,
        default=default,
    )


def dedupe_questions(questions: list[ClarificationQuestion]) -> list[ClarificationQuestion]:
    """Deduplicate clarification questions by canonical id."""

    merged: dict[str, ClarificationQuestion] = {}
    for question in questions:
        if question.id in merged:
            merged[question.id] = merge_questions(merged[question.id], question, prefer_new=False)
        else:
            merged[question.id] = question
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
    return "opcode" in text or re.search(r"\b00\b|\b01\b|\b10\b|\b11\b", text) is not None


def has_mux_input_count(text: str) -> bool:
    return re.search(r"\b2-to-1\b|\b4-to-1\b|\b8-to-1\b|\btwo-to-one\b|\bthree-to-one\b|\bone-bit inputs a and b\b", text) is not None


def has_select_mapping(text: str) -> bool:
    return "when select" in text or "otherwise" in text or "select is 0" in text or "select input" in text


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
                normalized_questions.append(question)
            else:
                normalized_questions.append(item)
        normalized["clarification_questions"] = normalized_questions
    return normalized


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
    "detect_explicit_details",
    "detect_requirement_family",
    "merge_with_local_ambiguity_policy",
    "normalize_analysis_payload",
    "normalize_requirement_analysis",
]
