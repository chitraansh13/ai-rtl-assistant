import json
import re
import time

from pydantic import ValidationError

from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.hardware_spec import DesignType, HardwareSpec
from rtl_assistant.models.reference import (
    ReferenceCorrection,
    ReferenceResolutionStatus,
)
from rtl_assistant.models.verification_plan import (
    VerificationPlan,
    VerificationPlanGenerationResult,
    VerificationPlanStatus,
)
from rtl_assistant.reference import DeterministicReferenceResolver, ReferenceResolver
from rtl_assistant.reference.handlers.alu import extract_alu_literal_vector
from rtl_assistant.verification_plan.prompts import (
    VERIFICATION_PLAN_PROMPT_VERSION,
    build_verification_plan_prompt,
    build_verification_plan_repair_prompt,
)


class AIVerificationPlanGenerator:
    """Generate a structured verification plan from a validated HardwareSpec."""

    def __init__(
        self,
        provider: LLMProvider,
        reference_resolver: ReferenceResolver | None = None,
    ) -> None:
        self.provider = provider
        self.reference_resolver = reference_resolver or DeterministicReferenceResolver()

    def generate(self, hardware_spec: HardwareSpec) -> VerificationPlanGenerationResult:
        """Generate and validate a verification plan with up to two attempts."""

        started_at = time.perf_counter()
        validation_errors: list[str] = []
        raw_model_output = ""
        reference_corrections: list[ReferenceCorrection] = []

        for attempt_number in range(1, 3):
            if attempt_number == 1:
                prompt = build_verification_plan_prompt(hardware_spec)
            else:
                prompt = build_verification_plan_repair_prompt(hardware_spec, raw_model_output, validation_errors)

            llm_response = self.provider.generate(prompt)
            raw_model_output = llm_response.response_text

            if not llm_response.success:
                return VerificationPlanGenerationResult(
                    status=VerificationPlanStatus.FAIL,
                    module_name=hardware_spec.module_name,
                    verification_plan=None,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    prompt_version=VERIFICATION_PLAN_PROMPT_VERSION,
                    attempts=attempt_number,
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    raw_model_output=raw_model_output or None,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                    validation_errors=validation_errors,
                    reference_corrections=reference_corrections,
                )

            json_object, json_error = extract_json_object(raw_model_output)
            if json_error is not None:
                validation_errors = [json_error]
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec=hardware_spec,
                        attempts=attempt_number,
                        raw_model_output=raw_model_output,
                        validation_errors=validation_errors,
                        started_at=started_at,
                        error_type="INVALID_PLAN_JSON",
                        error_message="Model output was not valid JSON after retry.",
                    )
                continue

            try:
                json_object = normalize_verification_plan_payload(json_object)
                verification_plan = VerificationPlan.model_validate(json_object)
            except ValidationError as exc:
                validation_errors = format_validation_errors(exc)
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec=hardware_spec,
                        attempts=attempt_number,
                        raw_model_output=raw_model_output,
                        validation_errors=validation_errors,
                        started_at=started_at,
                        error_type="VERIFICATION_PLAN_VALIDATION_FAILED",
                        error_message="Model output JSON did not satisfy the VerificationPlan schema after retry.",
                    )
                continue

            try:
                verification_plan, reference_corrections = apply_reference_resolution(
                    hardware_spec=hardware_spec,
                    verification_plan=verification_plan,
                    reference_resolver=self.reference_resolver,
                )
            except ValueError as exc:
                validation_errors = [str(exc)]
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec=hardware_spec,
                        attempts=attempt_number,
                        raw_model_output=raw_model_output,
                        validation_errors=validation_errors,
                        started_at=started_at,
                        error_type="REFERENCE_RESOLUTION_ERROR",
                        error_message=str(exc),
                        reference_corrections=reference_corrections,
                    )
                continue

            sanity_errors = run_verification_plan_sanity_checks(
                hardware_spec,
                verification_plan,
                self.reference_resolver,
            )
            if sanity_errors:
                validation_errors = sanity_errors
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec=hardware_spec,
                        attempts=attempt_number,
                        raw_model_output=raw_model_output,
                        validation_errors=validation_errors,
                        started_at=started_at,
                        reference_corrections=reference_corrections,
                    )
                continue

            return VerificationPlanGenerationResult(
                status=VerificationPlanStatus.SUCCESS,
                module_name=hardware_spec.module_name,
                verification_plan=verification_plan,
                provider=llm_response.provider,
                model=llm_response.model,
                prompt_version=VERIFICATION_PLAN_PROMPT_VERSION,
                attempts=attempt_number,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                raw_model_output=raw_model_output,
                error_type=None,
                error_message=None,
                validation_errors=[],
                reference_corrections=reference_corrections,
            )

        return self._failure_result(
            hardware_spec=hardware_spec,
            attempts=2,
            raw_model_output=raw_model_output,
            validation_errors=["Verification-plan generation exhausted its retry budget."],
            started_at=started_at,
            error_type="VERIFICATION_PLAN_RETRY_EXHAUSTED",
            error_message="Verification-plan generation exhausted its retry budget.",
            reference_corrections=reference_corrections,
        )

    def _failure_result(
        self,
        hardware_spec: HardwareSpec,
        attempts: int,
        raw_model_output: str,
        validation_errors: list[str],
        started_at: float,
        error_type: str | None = None,
        error_message: str | None = None,
        reference_corrections: list[ReferenceCorrection] | None = None,
    ) -> VerificationPlanGenerationResult:
        """Build a structured failure result."""

        resolved_error_type = error_type or derive_primary_error_type(validation_errors)
        resolved_error_message = error_message or (
            validation_errors[0] if validation_errors else "Verification-plan generation failed."
        )
        return VerificationPlanGenerationResult(
            status=VerificationPlanStatus.FAIL,
            module_name=hardware_spec.module_name,
            verification_plan=None,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            prompt_version=VERIFICATION_PLAN_PROMPT_VERSION,
            attempts=attempts,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            raw_model_output=raw_model_output or None,
            error_type=resolved_error_type,
            error_message=resolved_error_message,
            validation_errors=validation_errors,
            reference_corrections=reference_corrections or [],
        )


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


def normalize_verification_plan_payload(payload: dict) -> dict:
    """Repair small, obvious plan-payload representation mismatches before validation."""

    normalized = dict(payload)
    for field_name in ("coverage_targets", "assumptions", "notes"):
        normalized[field_name] = normalize_top_level_string_list(normalized.get(field_name), field_name)

    raw_test_cases = normalized.get("test_cases")
    if isinstance(raw_test_cases, list):
        normalized_test_cases: list[object] = []
        for item in raw_test_cases:
            if isinstance(item, dict):
                test_case = dict(item)
                test_case["category"] = normalize_test_category(test_case.get("category"))
                for field_name in ("setup", "stimulus", "expected", "covers"):
                    test_case[field_name] = normalize_string_list(test_case.get(field_name))
                normalized_test_cases.append(test_case)
            else:
                normalized_test_cases.append(item)
        normalized["test_cases"] = normalized_test_cases

    return normalized


def normalize_string_list(value: object) -> object:
    """Normalize obvious scalar-or-bulleted string encodings into a list of strings."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return normalize_mapping_to_string_list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if len(lines) > 1 and all(line.startswith(("-", "*")) for line in lines):
            items = [line[1:].strip() for line in lines if line[1:].strip()]
            if items:
                return items

        return [stripped]
    return value


def normalize_top_level_string_list(value: object, field_name: str) -> object:
    """Normalize top-level list-of-string fields with special handling for objects."""

    if value is None:
        return []
    if isinstance(value, str):
        return normalize_string_list(value)
    if isinstance(value, dict):
        return [normalize_named_object_to_string(value, field_name)]
    if isinstance(value, list):
        normalized_items: list[object] = []
        for item in value:
            if isinstance(item, str):
                normalized_items.append(item)
            elif isinstance(item, dict):
                normalized_items.append(normalize_named_object_to_string(item, field_name))
            elif item is None:
                continue
            else:
                normalized_items.append(stable_value_to_string(item))
        return normalized_items
    return value


def normalize_named_object_to_string(value: dict, field_name: str) -> str:
    """Convert an object-valued top-level descriptive field into one readable string."""

    if field_name == "coverage_targets":
        for key in ("description", "name", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    else:
        for key in ("description", "name", "title", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

    return stable_value_to_string(value)


def normalize_mapping_to_string_list(value: dict) -> list[str]:
    """Convert a simple mapping into a deterministic list of readable key=value strings."""

    normalized_items: list[str] = []
    for key, item in value.items():
        key_text = str(key).strip() or "value"
        normalized_items.append(f"{key_text}={stable_value_to_string(item)}")
    return normalized_items


def stable_value_to_string(value: object) -> str:
    """Convert JSON-like values into a stable readable string representation."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def normalize_test_category(value: object) -> object:
    """Map obvious category synonyms into the existing canonical TestCategory vocabulary."""

    if not isinstance(value, str):
        return value

    normalized = "_".join(value.strip().upper().split())
    category_map = {
        "LOGIC": "FUNCTIONAL",
        "BITWISE": "FUNCTIONAL",
        "ZERO_BEHAVIOR": "FUNCTIONAL",
        "ZERO": "FUNCTIONAL",
        "FLAGS": "FUNCTIONAL",
        "FLAG": "FUNCTIONAL",
        "FUNCTIONAL": "FUNCTIONAL",
        "ARITHMETIC": "ARITHMETIC",
        "BOUNDARY": "BOUNDARY",
        "EDGE_CASE": "EDGE_CASE",
        "EDGE": "EDGE_CASE",
        "CONTROL": "CONTROL",
        "RESET": "RESET",
        "STATE_TRANSITION": "STATE_TRANSITION",
        "STATE": "STATE_TRANSITION",
        "BASIC": "BASIC",
        "INVALID_OR_GUARDED": "INVALID_OR_GUARDED",
        "OTHER": "OTHER",
    }
    return category_map.get(normalized, "OTHER")


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


def apply_reference_resolution(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    reference_resolver: ReferenceResolver,
) -> tuple[VerificationPlan, list[ReferenceCorrection]]:
    """Canonicalize supported expected values through deterministic resolution."""

    corrected_test_cases = []
    corrections: list[ReferenceCorrection] = []

    for test_case in verification_plan.test_cases:
        resolution = reference_resolver.resolve(hardware_spec, test_case)

        if resolution.status == ReferenceResolutionStatus.ERROR:
            raise ValueError(
                "REFERENCE_RESOLUTION_ERROR: "
                + (resolution.error_message or "Deterministic reference resolution failed unexpectedly.")
            )

        if resolution.status != ReferenceResolutionStatus.RESOLVED:
            corrected_test_cases.append(test_case)
            continue

        deterministic_expected = resolution.canonical_expected
        if test_case.expected != deterministic_expected:
            corrections.append(
                ReferenceCorrection(
                    test_case_id=test_case.id,
                    resolver=resolution.resolver,
                    ai_expected=test_case.expected,
                    deterministic_expected=deterministic_expected,
                    explanation=resolution.explanation,
                )
            )
            corrected_test_cases.append(test_case.model_copy(update={"expected": deterministic_expected}))
        else:
            corrected_test_cases.append(test_case)

    corrected_payload = verification_plan.model_dump()
    corrected_payload["test_cases"] = [test_case.model_dump() for test_case in corrected_test_cases]
    corrected_plan = VerificationPlan.model_validate(corrected_payload)
    return corrected_plan, corrections


def run_verification_plan_sanity_checks(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    reference_resolver: ReferenceResolver,
) -> list[str]:
    """Run lightweight deterministic plan checks against the HardwareSpec."""

    errors: list[str] = []

    if verification_plan.module_name != hardware_spec.module_name:
        errors.append(
            f"MODULE_NAME_MISMATCH: Expected module {hardware_spec.module_name} but plan targets {verification_plan.module_name}."
        )

    if not verification_plan.test_cases:
        errors.append("INSUFFICIENT_TEST_CASES: Verification plan must include at least one test case.")
        return errors

    searchable_text = make_searchable_plan_text(verification_plan)
    errors.extend(derive_output_drive_errors(hardware_spec, verification_plan))

    if hardware_spec.reset is not None and not contains_any(searchable_text, ["reset", hardware_spec.reset.signal, "rst"]):
        errors.append("MISSING_RESET_TEST: HardwareSpec defines reset behavior but the plan does not clearly cover reset.")

    if hardware_spec.design_type == DesignType.SEQUENTIAL and not contains_any(
        searchable_text,
        ["clock", "edge", "rising", "falling", "increment", "decrement", "hold", "state"],
    ):
        errors.append(
            "MISSING_STATE_TRANSITION_TEST: Sequential HardwareSpec should include at least one clocked state-update test."
        )

    operation_errors = derive_operation_coverage_errors(hardware_spec, searchable_text)
    errors.extend(operation_errors)

    mux_errors = derive_mux_coverage_errors(hardware_spec, searchable_text)
    errors.extend(mux_errors)

    arithmetic_guardrail_errors = derive_arithmetic_guardrail_errors(
        hardware_spec,
        verification_plan,
        searchable_text,
        reference_resolver,
    )
    errors.extend(arithmetic_guardrail_errors)
    errors.extend(derive_sequential_guardrail_errors(hardware_spec, verification_plan))

    return errors


def make_searchable_plan_text(verification_plan: VerificationPlan) -> str:
    """Flatten plan text into a lowercased search surface for simple sanity checks."""

    parts = [
        verification_plan.strategy,
        *verification_plan.coverage_targets,
        *verification_plan.assumptions,
        *verification_plan.notes,
    ]
    for test_case in verification_plan.test_cases:
        parts.extend(
            [
                test_case.id,
                test_case.name,
                test_case.description,
                *test_case.setup,
                *test_case.stimulus,
                *test_case.expected,
                *test_case.covers,
            ]
        )
    return "\n".join(parts).lower()


def derive_operation_coverage_errors(hardware_spec: HardwareSpec, searchable_text: str) -> list[str]:
    """Check that explicitly listed operations are represented somewhere in the plan."""

    if not hardware_spec.behavior.operations:
        return []

    missing_operations: list[str] = []
    for operation in hardware_spec.behavior.operations:
        normalized = operation.strip().lower()
        if normalized == "mux":
            continue
        if normalized and normalized not in searchable_text:
            missing_operations.append(operation)

    if missing_operations:
        return [
            "MISSING_OPERATION_COVERAGE: Plan does not clearly reference operation coverage for "
            + ", ".join(missing_operations)
            + "."
        ]
    return []


def derive_mux_coverage_errors(hardware_spec: HardwareSpec, searchable_text: str) -> list[str]:
    """Perform a small obvious-coverage check for mux select mappings."""

    joined_operations = " ".join(hardware_spec.behavior.operations).lower()
    joined_tags = " ".join(hardware_spec.tags).lower()
    joined_rules = " ".join(hardware_spec.behavior.rules).lower()
    if "mux" not in joined_operations and "mux" not in joined_tags and "select" not in joined_rules:
        return []

    has_select_zero = contains_any(searchable_text, ["select=0", "select is 0", "select zero"])
    has_select_one = contains_any(searchable_text, ["select=1", "select is 1", "select one"])
    if has_select_zero and has_select_one:
        return []
    return [
        "MISSING_OPERATION_COVERAGE: Mux verification plan should clearly cover both specified select paths."
    ]


def derive_arithmetic_guardrail_errors(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    searchable_text: str,
    reference_resolver: ReferenceResolver,
) -> list[str]:
    """Apply a few lightweight arithmetic guardrails for unsigned ALU-like specs."""

    port_names = {port.name.lower() for port in hardware_spec.ports}
    has_carry_port = "carry" in port_names
    operations = {operation.strip().upper() for operation in hardware_spec.behavior.operations}
    has_add = "ADD" in operations
    has_sub = "SUB" in operations
    has_unsigned_data = any(
        port.direction.value == "input" and not port.signed and port.role.value == "data"
        for port in hardware_spec.ports
    )

    errors: list[str] = []

    if has_unsigned_data and contains_any(
        searchable_text,
        ["negative numbers", "negative number", "signed arithmetic", "signed overflow"],
    ):
        errors.append(
            "SIGNEDNESS_CONTRADICTION: Plan language contradicts the unsigned HardwareSpec semantics."
        )

    if has_carry_port and has_add and not contains_any(
        searchable_text,
        ["carry=1", "carry = 1", "carry equals 1", "carry asserted", "carry is 1"],
    ):
        errors.append(
            "MISSING_CARRY_ASSERT_TEST: Carry behavior is specified but the plan does not clearly include a carry-producing test."
        )

    errors.extend(
        derive_literal_vector_consistency_errors(
            hardware_spec,
            verification_plan,
            reference_resolver,
        )
    )

    return errors


def derive_output_drive_errors(hardware_spec: HardwareSpec, verification_plan: VerificationPlan) -> list[str]:
    """Reject obvious attempts to drive DUT output ports in setup or stimulus."""

    output_ports = [port.name for port in hardware_spec.ports if port.direction.value == "output"]
    if not output_ports:
        return []

    errors: list[str] = []
    for test_case in verification_plan.test_cases:
        for item in [*test_case.setup, *test_case.stimulus]:
            driven_signal = parse_driven_signal(item, output_ports)
            if driven_signal is None:
                continue
            errors.append(
                "ILLEGAL_OUTPUT_DRIVE: "
                + f"Test '{test_case.id}' attempts to drive output port '{driven_signal}'. "
                + "Sequential state must be reached through legal inputs and clock transitions."
            )
    return errors


def derive_sequential_guardrail_errors(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
) -> list[str]:
    """Apply lightweight sequential guardrails for clock, reset, and simple counter transitions."""

    if hardware_spec.design_type != DesignType.SEQUENTIAL:
        return []

    errors: list[str] = []
    for test_case in verification_plan.test_cases:
        test_text = make_test_case_text(test_case)
        touches_state = test_mentions_state_behavior(hardware_spec, test_case)
        has_active_event = test_has_active_clock_event(hardware_spec, test_text)
        mentions_reset = reset_test_mentions(hardware_spec, test_case)

        if touches_state and not has_active_event:
            errors.append(
                "MISSING_ACTIVE_CLOCK_EVENT: "
                + f"Test '{test_case.id}' describes a sequential state transition without referencing the active clock event."
            )

        if (
            mentions_reset
            and hardware_spec.reset is not None
            and hardware_spec.reset.type.value == "synchronous"
            and not has_active_event
        ):
            errors.append(
                "SYNCHRONOUS_RESET_WITHOUT_CLOCK_EDGE: "
                + f"Test '{test_case.id}' describes synchronous reset behavior without an active clock edge."
            )

    errors.extend(derive_counter_transition_errors(hardware_spec, verification_plan))
    errors.extend(derive_counter_precondition_errors(hardware_spec, verification_plan))
    return errors


def derive_counter_transition_errors(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
) -> list[str]:
    """Validate simple explicit counter transitions when enough literals are present."""

    if not is_counter_like_spec(hardware_spec):
        return []

    count_width = find_port_width(hardware_spec, "count")
    if count_width is None:
        return []

    modulus = 1 << count_width
    direction = infer_counter_direction(hardware_spec)

    errors: list[str] = []
    for test_case in verification_plan.test_cases:
        transition = extract_counter_transition(test_case, hardware_spec)
        if transition is None:
            continue

        start_count = transition["start_count"]
        edge_count = transition["edge_count"]
        expected_count = transition["expected_count"]
        enable_state = transition["enable_state"]

        if enable_state is False:
            computed = start_count
        elif direction == "down":
            computed = (start_count - edge_count) % modulus
        else:
            computed = (start_count + edge_count) % modulus

        if expected_count != computed:
            errors.append(
                "INCORRECT_STATE_TRANSITION_EXPECTATION: "
                + f"Test '{test_case.id}' expects count={expected_count} after {edge_count} active edge(s) from count={start_count}; "
                + f"expected count is {computed} for this {count_width}-bit {direction}-counter."
            )

    return errors


def derive_counter_precondition_errors(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
) -> list[str]:
    """Flag counter tests that expect nontrivial state without establishing or stating a legal precondition."""

    if not is_counter_like_spec(hardware_spec):
        return []

    reset_default = None
    if hardware_spec.reset is not None:
        raw_default = hardware_spec.reset.reset_values.get("count")
        if isinstance(raw_default, int):
            reset_default = raw_default

    errors: list[str] = []
    for test_case in verification_plan.test_cases:
        test_text = make_test_case_text(test_case)
        expected_count = extract_expected_count(" ".join(test_case.expected))
        has_precondition = counter_state_precondition_present(test_case)

        if contains_any(test_text, ["hold", "remains", "unchanged"]) and expected_count is not None:
            if expected_count != reset_default and not has_precondition:
                errors.append(
                    "UNESTABLISHED_PRECONDITION: "
                    + f"Test '{test_case.id}' expects count={expected_count} during a hold-style check without establishing or stating how that state was legally reached."
                )

        if contains_any(test_text, ["wrap", "wraparound"]) and not has_precondition:
            errors.append(
                "UNESTABLISHED_PRECONDITION: "
                + f"Test '{test_case.id}' describes wraparound behavior without establishing or stating the required boundary state."
            )

    return errors


def derive_literal_vector_consistency_errors(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    reference_resolver: ReferenceResolver,
) -> list[str]:
    """Validate simple explicit ALU literal vectors already present in the generated plan."""

    operations = {operation.strip().upper() for operation in hardware_spec.behavior.operations}
    supported_operations = {"ADD", "SUB", "AND", "OR"}
    if not operations.intersection(supported_operations):
        return []

    errors: list[str] = []
    for test_case in verification_plan.test_cases:
        resolution = reference_resolver.resolve(hardware_spec, test_case)
        if resolution.status != ReferenceResolutionStatus.RESOLVED:
            continue
        if resolution.resolver != "unsigned_fixed_width_alu":
            continue

        literal_vector = extract_alu_literal_vector(hardware_spec, test_case)
        expected_values = {
            key: value
            for key, value in {
                "result": literal_vector.expected_result,
                "carry": literal_vector.expected_carry,
                "zero": literal_vector.expected_zero,
            }.items()
            if isinstance(value, int)
        }
        if not expected_values:
            continue
        if not reference_expected_matches(expected_values, resolution.expected_values):
            errors.append(
                "INCORRECT_EXPECTED_VALUE: "
                + f"Test '{test_case.id}' includes explicit expected values that do not match the deterministic ALU reference result."
            )

    return errors


def reference_expected_matches(
    parsed_values: dict[str, int | str],
    deterministic_expected: dict[str, int | str],
) -> bool:
    """Return True when explicit expected literals match the deterministic reference values."""

    for signal_name, deterministic_value in deterministic_expected.items():
        explicit_value = parsed_values.get(signal_name)
        if explicit_value is None:
            continue
        if explicit_value != deterministic_value:
            return False
    return True


def find_port_width(hardware_spec: HardwareSpec, port_name: str) -> int | None:
    """Return the width of a named port if present."""

    for port in hardware_spec.ports:
        if port.name == port_name:
            return port.width
    return None


def parse_driven_signal(text: str, signal_names: list[str]) -> str | None:
    """Parse obvious assignment-style writes and return the driven output signal."""

    if not signal_names:
        return None
    signal_pattern = "|".join(re.escape(name) for name in signal_names)
    explicit_match = re.search(
        rf"\b(?:drive|set|force)\s+({signal_pattern})\s*=",
        text,
        re.IGNORECASE,
    )
    if explicit_match is not None:
        return explicit_match.group(1)

    bare_assignment = re.search(
        rf"^\s*({signal_pattern})\s*=",
        text,
        re.IGNORECASE,
    )
    if bare_assignment is not None:
        return bare_assignment.group(1)

    return None


def make_test_case_text(test_case) -> str:
    """Flatten one test case into a lowercased search surface."""

    return "\n".join(
        [
            test_case.id,
            test_case.name,
            test_case.description,
            *test_case.setup,
            *test_case.stimulus,
            *test_case.expected,
            *test_case.covers,
        ]
    ).lower()


def reset_test_mentions(hardware_spec: HardwareSpec, test_case) -> bool:
    """Return True only when a test appears to exercise active reset behavior."""

    if hardware_spec.reset is None:
        return False

    if getattr(test_case, "category", None) is not None and str(test_case.category.value) == "RESET":
        return True

    test_text = make_test_case_text(test_case)
    reset_signal = hardware_spec.reset.signal.lower()
    active_high = hardware_spec.reset.polarity.value == "active_high"

    if contains_any(test_text, ["reset behavior", "resetting"]):
        return True

    if active_high:
        active_patterns = [
            rf"\b{re.escape(reset_signal)}\s*=\s*1\b",
            rf"\bassert\s+{re.escape(reset_signal)}\b",
            rf"\bassert\s+reset\b",
            r"\bactive-high reset\b",
            r"\breset active\b",
        ]
    else:
        active_patterns = [
            rf"\b{re.escape(reset_signal)}\s*=\s*0\b",
            rf"\bassert\s+{re.escape(reset_signal)}\b",
            rf"\bassert\s+reset\b",
            r"\bactive-low reset\b",
            r"\breset active\b",
        ]

    return any(re.search(pattern, test_text, re.IGNORECASE) for pattern in active_patterns)


def test_mentions_state_behavior(hardware_spec: HardwareSpec, test_case) -> bool:
    """Return True when a sequential test appears to describe state change or hold behavior."""

    test_text = make_test_case_text(test_case)
    output_names = [port.name.lower() for port in hardware_spec.ports if port.direction.value == "output"]
    state_words = [
        *output_names,
        "increment",
        "decrement",
        "hold",
        "wrap",
        "wraparound",
        "state",
        "count",
    ]
    return contains_any(test_text, state_words)


def test_has_active_clock_event(hardware_spec: HardwareSpec, test_text: str) -> bool:
    """Return True when a test clearly references the active clock event."""

    if hardware_spec.clock is None:
        return False

    generic_phrases = ["active edge", "next active edge", "0->1 transition", "1->0 transition"]
    if hardware_spec.clock.edge.value == "positive":
        phrases = [*generic_phrases, "rising edge", "positive edge", "posedge"]
    else:
        phrases = [*generic_phrases, "falling edge", "negative edge", "negedge"]
    return contains_any(test_text, phrases)


def is_counter_like_spec(hardware_spec: HardwareSpec) -> bool:
    """Heuristically detect the current counter-like sequential spec family."""

    operations = {operation.strip().upper() for operation in hardware_spec.behavior.operations}
    tags = {tag.strip().lower() for tag in hardware_spec.tags}
    return (
        "counter" in hardware_spec.module_name.lower()
        or "counter" in tags
        or "INCREMENT" in operations
    )


def counter_state_precondition_present(test_case) -> bool:
    """Return True when a counter test states or establishes the needed state legally."""

    setup_text = " ".join(test_case.setup)
    description_text = test_case.description
    if extract_count_precondition(setup_text) is not None:
        return True
    if extract_count_precondition(description_text) is not None:
        return True

    text = make_test_case_text(test_case)
    return contains_any(
        text,
        [
            "reset to known state",
            "reset counter to 0",
            "bring count to",
            "count has legally reached",
            "count has reached",
            "apply enough active edges",
            "apply enough rising edges",
            "apply enough falling edges",
        ],
    )


def infer_counter_direction(hardware_spec: HardwareSpec) -> str:
    """Infer counter direction conservatively from the HardwareSpec."""

    text = " ".join(
        [
            hardware_spec.description or "",
            *hardware_spec.behavior.rules,
            *hardware_spec.behavior.operations,
            *hardware_spec.tags,
        ]
    ).lower()
    if "down" in text and "up" not in text:
        return "down"
    return "up"


def extract_counter_transition(test_case, hardware_spec: HardwareSpec) -> dict[str, int | bool] | None:
    """Extract a simple explicit counter transition if one is clearly stated."""

    setup_text = " ".join(test_case.setup)
    stimulus_text = " ".join(test_case.stimulus)
    expected_text = " ".join(test_case.expected)
    combined_text = " ".join([setup_text, stimulus_text, expected_text, test_case.description, *test_case.covers])

    start_count = extract_count_precondition(setup_text) or extract_count_precondition(test_case.description)
    expected_count = extract_expected_count(expected_text)
    edge_count = extract_active_edge_count(hardware_spec, combined_text)
    enable_state = extract_enable_state(hardware_spec, combined_text)

    if start_count is None or expected_count is None or edge_count is None:
        return None

    return {
        "start_count": start_count,
        "expected_count": expected_count,
        "edge_count": edge_count,
        "enable_state": enable_state,
    }


def extract_count_precondition(text: str) -> int | None:
    """Extract a conceptual starting count without treating it as a drive action."""

    patterns = [
        r"\bstarting\s+count\s*=\s*(\d+)\b",
        r"\bstart\s+count\s*=\s*(\d+)\b",
        r"\bcount\s+has\s+reached\s+(\d+)\b",
        r"\bcount\s+reaches\s+(\d+)\b",
        r"\bbring\s+count\s+to\s+(\d+)\b",
        r"\breach\s+count\s*=\s*(\d+)\b",
        r"\breach\s+count\s+(\d+)\b",
        r"\bwhen\s+count\s*=\s*(\d+)\b",
        r"\bat\s+count\s*=\s*(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None:
            return int(match.group(1), 10)
    return None


def extract_expected_count(text: str) -> int | None:
    """Extract an expected count value from expected text."""

    match = re.search(r"\bcount\s*=\s*(\d+)\b", text, re.IGNORECASE)
    if match is not None:
        return int(match.group(1), 10)
    match = re.search(r"\bcount\s+equals\s+(\d+)\b", text, re.IGNORECASE)
    if match is not None:
        return int(match.group(1), 10)
    return None


def extract_active_edge_count(hardware_spec: HardwareSpec, text: str) -> int | None:
    """Extract the number of active clock events referenced by the test."""

    if hardware_spec.clock is None:
        return None

    if hardware_spec.clock.edge.value == "positive":
        edge_pattern = r"(?:rising|positive|active)\s+edge|0->1\s+transition"
    else:
        edge_pattern = r"(?:falling|negative|active)\s+edge|1->0\s+transition"

    patterns = [
        rf"\b(\d+)\s+{edge_pattern}s?\b",
        rf"\bone\s+{edge_pattern}\b",
        rf"\bnext\s+{edge_pattern}\b",
        rf"\ban?\s+additional\s+{edge_pattern}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        if match.lastindex and match.group(1):
            return int(match.group(1), 10)
        return 1
    return None


def extract_enable_state(hardware_spec: HardwareSpec, text: str) -> bool | None:
    """Extract whether enable is explicitly asserted or deasserted."""

    enable_names = [
        port.name
        for port in hardware_spec.ports
        if port.direction.value == "input" and port.name.lower() in {"en", "enable"}
    ]
    if not enable_names:
        return True

    pattern = "|".join(re.escape(name) for name in enable_names)
    if re.search(rf"\b(?:{pattern})\s*=\s*1\b", text, re.IGNORECASE) or contains_any(text, ["enable high", "enabled"]):
        return True
    if re.search(rf"\b(?:{pattern})\s*=\s*0\b", text, re.IGNORECASE) or contains_any(text, ["enable low", "disabled"]):
        return False
    return None


def contains_any(text: str, phrases: list[str]) -> bool:
    """Return True if any phrase appears in normalized text."""

    normalized = " ".join(text.lower().split())
    return any(" ".join(phrase.lower().split()) in normalized for phrase in phrases)


def derive_primary_error_type(errors: list[str]) -> str:
    """Extract the primary structured error type from local errors."""

    if not errors:
        return "VERIFICATION_PLAN_RETRY_EXHAUSTED"
    prefix = errors[0].split(":", 1)[0].strip()
    return prefix or "VERIFICATION_PLAN_RETRY_EXHAUSTED"
