import re
import time

from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.hardware_spec import DesignType, HardwareSpec
from rtl_assistant.models.testbench_generation import (
    TestbenchGenerationMode,
    TestbenchGenerationResult,
    TestbenchGenerationStatus,
)
from rtl_assistant.models.verification_plan import VerificationPlan
from rtl_assistant.testbench.prompts import (
    TESTBENCH_PROMPT_VERSION,
    build_testbench_generation_prompt,
    build_testbench_repair_prompt,
)


FORBIDDEN_DUT_REDEFINITION_TEMPLATE = "DUT_REDEFINED: Generated testbench redefines the DUT module '{module_name}'."


class AITestbenchGenerator:
    """Generate self-checking SystemVerilog testbenches from structured inputs."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def generate(
        self,
        hardware_spec: HardwareSpec,
        verification_plan: VerificationPlan,
    ) -> TestbenchGenerationResult:
        """Generate and structurally validate a testbench with up to two attempts."""

        started_at = time.perf_counter()
        raw_response = ""
        errors: list[str] = []

        for attempt_number in range(1, 3):
            if attempt_number == 1:
                prompt = build_testbench_generation_prompt(hardware_spec, verification_plan)
            else:
                prompt = build_testbench_repair_prompt(hardware_spec, verification_plan, raw_response, errors)

            llm_response = self.provider.generate(prompt)
            raw_response = llm_response.response_text

            if not llm_response.success:
                return TestbenchGenerationResult(
                    status=TestbenchGenerationStatus.FAIL,
                    generation_mode=TestbenchGenerationMode.AI,
                    module_name=hardware_spec.module_name,
                    testbench_text=None,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    prompt_version=TESTBENCH_PROMPT_VERSION,
                    attempts=attempt_number,
                    test_count=len(verification_plan.test_cases),
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    raw_response=raw_response or None,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                    validation_errors=errors,
                )

            testbench_text, extract_errors = extract_testbench_module(raw_response)
            if testbench_text is None:
                errors = extract_errors
                if attempt_number == 2:
                    return self._failure_result(hardware_spec, attempt_number, raw_response, errors, started_at)
                continue

            errors = run_testbench_sanity_checks(hardware_spec, verification_plan, testbench_text)
            if errors:
                if attempt_number == 2:
                    return self._failure_result(hardware_spec, attempt_number, raw_response, errors, started_at)
                continue

            return TestbenchGenerationResult(
                status=TestbenchGenerationStatus.SUCCESS,
                generation_mode=TestbenchGenerationMode.AI,
                module_name=hardware_spec.module_name,
                testbench_text=testbench_text,
                provider=llm_response.provider,
                model=llm_response.model,
                prompt_version=TESTBENCH_PROMPT_VERSION,
                attempts=attempt_number,
                test_count=len(verification_plan.test_cases),
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                raw_response=raw_response,
                error_type=None,
                error_message=None,
                validation_errors=[],
            )

        return self._failure_result(
            hardware_spec,
            2,
            raw_response,
            ["TESTBENCH_GENERATION_RETRY_EXHAUSTED: Testbench generation exhausted its retry budget."],
            started_at,
            error_type="TESTBENCH_GENERATION_RETRY_EXHAUSTED",
        )

    def _failure_result(
        self,
        hardware_spec: HardwareSpec,
        attempts: int,
        raw_response: str,
        errors: list[str],
        started_at: float,
        error_type: str | None = None,
    ) -> TestbenchGenerationResult:
        """Build a structured failure result from extraction or sanity errors."""

        resolved_error_type = error_type or derive_primary_error_type(errors)
        return TestbenchGenerationResult(
            status=TestbenchGenerationStatus.FAIL,
            generation_mode=TestbenchGenerationMode.AI,
            module_name=hardware_spec.module_name,
            testbench_text=None,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            prompt_version=TESTBENCH_PROMPT_VERSION,
            attempts=attempts,
            test_count=None,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            raw_response=raw_response or None,
            error_type=resolved_error_type,
            error_message=errors[0] if errors else "Testbench generation failed.",
            validation_errors=errors,
        )


def extract_testbench_module(text: str) -> tuple[str | None, list[str]]:
    """Extract one credible testbench module from raw model output."""

    stripped = strip_single_markdown_fence(text.strip())
    candidate = stripped if stripped is not None else text.strip()
    if not candidate:
        return None, ["EMPTY_MODEL_RESPONSE: Model returned empty text."]

    module_pattern = re.compile(r"\bmodule\s+[A-Za-z_][A-Za-z0-9_$]*\b", re.MULTILINE)
    modules = list(module_pattern.finditer(candidate))
    if len(modules) == 0:
        return None, ["TESTBENCH_NOT_FOUND: No valid module declaration was found in model output."]
    if len(modules) > 1:
        return None, ["MULTIPLE_MODULES: Model output appears to contain multiple module declarations."]

    end_index = candidate.rfind("endmodule")
    if end_index == -1 or end_index < modules[0].start():
        return None, ["TESTBENCH_NOT_FOUND: No matching endmodule was found in model output."]

    extracted = candidate[modules[0].start() : end_index + len("endmodule")].strip()
    return extracted, []


def strip_single_markdown_fence(text: str) -> str | None:
    """Strip one outer Markdown code fence if the whole response is fenced."""

    lines = text.splitlines()
    if len(lines) < 3:
        return None
    if not lines[0].strip().startswith("```"):
        return None
    if lines[-1].strip() != "```":
        return None
    inner = "\n".join(lines[1:-1]).strip()
    return inner or None


def run_testbench_sanity_checks(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    testbench_text: str,
) -> list[str]:
    """Run lightweight deterministic checks on generated testbench text."""

    errors: list[str] = []
    module_matches = list(re.finditer(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b", testbench_text, re.MULTILINE))
    if len(module_matches) != 1:
        if len(module_matches) > 1:
            errors.append("MULTIPLE_MODULES: Generated testbench contains multiple module declarations.")
        else:
            errors.append("TESTBENCH_NOT_FOUND: Generated testbench does not contain a valid module declaration.")
        return errors

    tb_module_name = module_matches[0].group(1)
    if tb_module_name == hardware_spec.module_name:
        errors.append(FORBIDDEN_DUT_REDEFINITION_TEMPLATE.format(module_name=hardware_spec.module_name))

    instantiation_match = find_dut_instantiation(hardware_spec.module_name, testbench_text)
    if instantiation_match is None:
        errors.append(
            f"DUT_INSTANTIATION_MISSING: Generated testbench does not clearly instantiate DUT module '{hardware_spec.module_name}'."
        )
    else:
        port_map_text = instantiation_match.group(2)
        for port in hardware_spec.ports:
            if not re.search(rf"\.{re.escape(port.name)}\s*\(", port_map_text):
                errors.append(f"MISSING_REQUIRED_PORT: DUT port '{port.name}' is missing from the testbench instantiation.")

    errors.extend(validate_output_ports_not_driven(hardware_spec, testbench_text))
    errors.extend(validate_verification_plan_coverage(verification_plan, testbench_text))
    errors.extend(validate_expected_output_checks(hardware_spec, verification_plan, testbench_text))
    errors.extend(validate_shared_check_task_usage(testbench_text))
    errors.extend(validate_stimulus_process_structure(hardware_spec, testbench_text))
    errors.extend(validate_delay_placement(testbench_text))
    errors.extend(validate_boolean_expression_safety(testbench_text))
    errors.extend(validate_clock_and_reset_usage(hardware_spec, testbench_text))
    errors.extend(validate_finish_and_self_checking(verification_plan, testbench_text))

    return errors


def find_dut_instantiation(dut_module_name: str, text: str) -> re.Match[str] | None:
    """Find a plausible DUT instantiation."""

    pattern = re.compile(
        rf"\b{re.escape(dut_module_name)}\b\s+(?:#\s*\(.*?\)\s*)?([A-Za-z_][A-Za-z0-9_$]*)\s*\((.*?)\)\s*;",
        re.DOTALL,
    )
    return pattern.search(text)


def validate_output_ports_not_driven(hardware_spec: HardwareSpec, testbench_text: str) -> list[str]:
    """Reject obvious procedural or continuous writes to DUT output-connected signals."""

    errors: list[str] = []
    output_names = [port.name for port in hardware_spec.ports if port.direction.value == "output"]
    for output_name in output_names:
        if re.search(rf"(?m)^\s*assign\s+{re.escape(output_name)}\s*=", testbench_text):
            errors.append(
                f"ILLEGAL_OUTPUT_DRIVE: Generated testbench contains continuous assignment to DUT output signal '{output_name}'."
            )
        if re.search(rf"(?m)^\s*{re.escape(output_name)}\s*(?:<=|=)\s*", testbench_text):
            errors.append(
                f"ILLEGAL_OUTPUT_DRIVE: Generated testbench directly assigns DUT output signal '{output_name}'."
            )
    return errors


def validate_verification_plan_coverage(
    verification_plan: VerificationPlan,
    testbench_text: str,
) -> list[str]:
    """Require every VerificationPlan test-case id to appear in the generated testbench."""

    missing_ids = [
        test_case.id
        for test_case in verification_plan.test_cases
        if test_case.id not in testbench_text
    ]
    if not missing_ids:
        return []

    return [
        "MISSING_TEST_CASE_IMPLEMENTATION: Generated testbench does not implement verification-plan tests: "
        + ", ".join(missing_ids)
    ]


def validate_expected_output_checks(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    testbench_text: str,
) -> list[str]:
    """Require each test implementation to reference the outputs it plans to check."""

    output_names = [port.name for port in hardware_spec.ports if port.direction.value == "output"]
    test_ids = [test_case.id for test_case in verification_plan.test_cases]
    missing_checks: list[str] = []

    for index, test_case in enumerate(verification_plan.test_cases):
        expected_outputs = extract_expected_output_names(test_case.expected, output_names)
        if not expected_outputs:
            continue

        test_region = extract_test_region(testbench_text, test_case.id, test_ids[index + 1 :])
        if test_region is None:
            continue

        absent_outputs = [
            output_name
            for output_name in expected_outputs
            if not has_output_comparison(test_region, output_name)
        ]
        if absent_outputs:
            missing_checks.append(f"{test_case.id} -> {', '.join(absent_outputs)}")

    if not missing_checks:
        return []

    return [
        "MISSING_EXPECTED_CHECK: Generated testbench omits planned expected-output checks for: "
        + "; ".join(missing_checks)
    ]


def validate_shared_check_task_usage(testbench_text: str) -> list[str]:
    """Reject generic shared output-checking tasks that obscure per-test planned checks."""

    for shared_check_task in re.finditer(
        r"\btask\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b[\s\S]*?\bendtask\b",
        testbench_text,
        re.IGNORECASE,
    ):
        task_text = shared_check_task.group(0)
        task_name = shared_check_task.group(1)
        if "expected_" not in task_text:
            continue
        if "check" not in task_name.lower():
            continue
        return [
            "DISALLOWED_SHARED_CHECK_TASK: Generated testbench uses a shared output-checking task instead of explicit inline per-test comparisons."
        ]

    return []


def validate_stimulus_process_structure(
    hardware_spec: HardwareSpec,
    testbench_text: str,
) -> list[str]:
    """Conservatively reject obvious multiple concurrent stimulus processes driving DUT inputs."""

    input_names = [port.name for port in hardware_spec.ports if port.direction.value == "input"]
    if not input_names:
        return []

    initial_bodies = extract_initial_block_bodies(testbench_text)
    if len(initial_bodies) <= 1:
        return []

    stimulus_blocks = [
        body
        for body in initial_bodies
        if block_drives_any_signal(body, input_names)
    ]
    if len(stimulus_blocks) <= 1:
        return []

    if hardware_spec.design_type == DesignType.SEQUENTIAL and hardware_spec.clock is not None:
        clock_name = hardware_spec.clock.signal
        non_clock_stimulus_blocks = [
            body
            for body in stimulus_blocks
            if not is_clock_generation_block(body, clock_name)
        ]
        if len(non_clock_stimulus_blocks) <= 1:
            return []

    return [
        "MULTIPLE_STIMULUS_PROCESSES: Generated testbench appears to contain multiple concurrent initial blocks driving DUT input signals."
    ]


def validate_delay_placement(testbench_text: str) -> list[str]:
    """Reject obvious invalid delay controls placed before structural keywords."""

    invalid_pattern = re.compile(r"#\s*(?:\(\s*\d+\s*\)|\d+)\s*(begin|end|else)\b", re.IGNORECASE)
    match = invalid_pattern.search(testbench_text)
    if match is None:
        return []

    keyword = match.group(1)
    return [
        f"INVALID_DELAY_PLACEMENT: Generated testbench places a delay control directly before structural keyword '{keyword}'."
    ]


def validate_boolean_expression_safety(testbench_text: str) -> list[str]:
    """Reject obvious invalid or unsafe boolean operators in self-checking conditions."""

    errors: list[str] = []
    for condition_text in extract_if_conditions(testbench_text):
        normalized_condition = normalize_condition_text(condition_text)
        if re.search(r"\b(and|or)\b", normalized_condition, re.IGNORECASE):
            errors.append(
                "INVALID_BOOLEAN_OPERATOR: Generated testbench uses English boolean operator text inside an if-condition."
            )
            break

        mismatch_count = len(re.findall(r"!==|!=", normalized_condition))
        has_or = "||" in normalized_condition
        has_and = "&&" in normalized_condition
        if mismatch_count >= 2 and has_and and not has_or:
            errors.append(
                "UNSAFE_MULTI_OUTPUT_CHECK: Generated testbench combines multiple mismatch predicates using only logical AND, so a partial output mismatch could be missed."
            )
            break

    return errors


def validate_clock_and_reset_usage(hardware_spec: HardwareSpec, testbench_text: str) -> list[str]:
    """Check basic sequential testbench requirements for clock and reset handling."""

    errors: list[str] = []
    if hardware_spec.design_type == DesignType.SEQUENTIAL:
        if hardware_spec.clock is None:
            errors.append("CLOCK_GENERATION_MISSING: Sequential HardwareSpec is missing clock metadata.")
            return errors

        clock_name = hardware_spec.clock.signal
        has_clock_logic = (
            re.search(rf"\balways\b[\s\S]*?\b{re.escape(clock_name)}\s*=\s*~\s*{re.escape(clock_name)}\b", testbench_text)
            or re.search(rf"\bforever\b[\s\S]*?\b{re.escape(clock_name)}\s*=\s*~\s*{re.escape(clock_name)}\b", testbench_text)
            or re.search(rf"#\s*\d+[\s\S]*?\b{re.escape(clock_name)}\s*=\s*~\s*{re.escape(clock_name)}\b", testbench_text)
        )
        if not has_clock_logic:
            errors.append(
                f"CLOCK_GENERATION_MISSING: Sequential testbench does not clearly generate or toggle clock '{clock_name}'."
            )

        if hardware_spec.reset is not None and hardware_spec.reset.signal not in testbench_text:
            errors.append(
                f"RESET_REFERENCE_MISSING: Generated testbench does not clearly reference reset signal '{hardware_spec.reset.signal}'."
            )
    else:
        if hardware_spec.clock is None:
            has_unexpected_clock_logic = (
                re.search(r"\bforever\b[\s\S]*?\bclk\s*=\s*~\s*clk\b", testbench_text)
                or re.search(r"\balways\s*#\s*\d+[\s\S]*?\bclk\s*=\s*~\s*clk\b", testbench_text)
            )
            if has_unexpected_clock_logic:
                errors.append(
                    "UNEXPECTED_CLOCK_LOGIC: Combinational testbench should not generate invented clock logic when the HardwareSpec has no clock port."
                )

    return errors


def validate_finish_and_self_checking(
    verification_plan: VerificationPlan,
    testbench_text: str,
) -> list[str]:
    """Check for finish, comparisons, and failure-reporting behavior."""

    del verification_plan
    errors: list[str] = []
    if "$finish" not in testbench_text:
        errors.append("MISSING_FINISH: Generated testbench does not contain $finish.")

    has_comparison = any(operator in testbench_text for operator in ("!==", "===", "!=", "=="))
    has_pass_fail_text = any(marker in testbench_text for marker in ("FAIL", "PASS", "failed_tests", "failed_tests++"))
    if not has_comparison or not has_pass_fail_text:
        errors.append(
            "SELF_CHECKING_MISSING: Generated testbench does not clearly contain self-checking PASS/FAIL comparison logic."
        )

    if not re.search(r"\bfailed_tests\b", testbench_text) and not re.search(r"\bfail(?:ed)?_count\b", testbench_text):
        errors.append(
            "FAILURE_COUNT_MISSING: Generated testbench does not clearly maintain a failure-count mechanism."
        )

    has_final_summary = (
        re.search(r'(?i)\$display\s*\(\s*"[^"]*failed tests[^"]*"', testbench_text)
        or re.search(r"(?i)\$display\s*\(\s*\"[^\"]*failed[^\"]*\"", testbench_text)
    )
    if not has_final_summary:
        errors.append(
            "MISSING_FINAL_SUMMARY: Generated testbench does not clearly print a final failed-test summary before $finish."
        )

    return errors


def derive_primary_error_type(errors: list[str]) -> str:
    """Extract the primary structured error type from local errors."""

    if not errors:
        return "TESTBENCH_GENERATION_RETRY_EXHAUSTED"
    return errors[0].split(":", 1)[0].strip() or "TESTBENCH_GENERATION_RETRY_EXHAUSTED"


def extract_if_conditions(testbench_text: str) -> list[str]:
    """Extract simple if-condition text with a conservative parenthesis matcher."""

    conditions: list[str] = []
    search_start = 0
    while True:
        if_match = re.search(r"\bif\s*\(", testbench_text[search_start:], re.IGNORECASE)
        if if_match is None:
            return conditions

        open_paren_index = search_start + if_match.end() - 1
        close_paren_index = find_matching_paren(testbench_text, open_paren_index)
        if close_paren_index is None:
            return conditions

        conditions.append(testbench_text[open_paren_index + 1 : close_paren_index])
        search_start = close_paren_index + 1


def find_matching_paren(text: str, open_paren_index: int) -> int | None:
    """Find the matching closing parenthesis for one opening parenthesis."""

    depth = 0
    for index in range(open_paren_index, len(text)):
        character = text[index]
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def normalize_condition_text(condition_text: str) -> str:
    """Strip comments and string literals from a condition before heuristic checks."""

    without_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', condition_text)
    without_line_comments = re.sub(r"//.*", "", without_strings)
    without_block_comments = re.sub(r"/\*.*?\*/", "", without_line_comments, flags=re.DOTALL)
    return without_block_comments


def extract_expected_output_names(expected_items: list[str], output_names: list[str]) -> list[str]:
    """Return the DUT output names explicitly represented in one test's expected list."""

    matched_outputs: list[str] = []
    combined_expected = "\n".join(expected_items)
    for output_name in output_names:
        if re.search(rf"\b{re.escape(output_name)}\b", combined_expected):
            matched_outputs.append(output_name)
    return matched_outputs


def has_output_comparison(test_region: str, output_name: str) -> bool:
    """Return True when one output appears to participate in an actual comparison."""

    return bool(
        re.search(
            rf"\b{re.escape(output_name)}\b\s*(?:!==|!=|===|==)",
            test_region,
        )
        or re.search(
            rf"(?:!==|!=|===|==)\s*\b{re.escape(output_name)}\b",
            test_region,
        )
    )


def extract_test_region(testbench_text: str, test_id: str, following_ids: list[str]) -> str | None:
    """Extract one test's approximate implementation region using preserved test IDs."""

    start_index = testbench_text.find(test_id)
    if start_index == -1:
        return None

    end_index = len(testbench_text)
    for following_id in following_ids:
        candidate_index = testbench_text.find(following_id, start_index + len(test_id))
        if candidate_index != -1:
            end_index = candidate_index
            break

    return testbench_text[start_index:end_index]


def extract_initial_block_bodies(testbench_text: str) -> list[str]:
    """Extract initial-block bodies with a small non-parser heuristic."""

    bodies: list[str] = []
    for match in re.finditer(r"\binitial\b", testbench_text):
        start_index = match.end()
        block_text = testbench_text[start_index:]
        begin_match = re.match(r"\s*begin\b", block_text)
        if begin_match is not None:
            begin_index = start_index + begin_match.end()
            end_index = find_matching_end(testbench_text, begin_index)
            if end_index is not None:
                bodies.append(testbench_text[begin_index:end_index])
            continue

        semicolon_index = testbench_text.find(";", start_index)
        if semicolon_index != -1:
            bodies.append(testbench_text[start_index:semicolon_index])

    return bodies


def find_matching_end(text: str, start_index: int) -> int | None:
    """Find the end of a begin/end block using token counting."""

    token_pattern = re.compile(r"\bbegin\b|\bend\b", re.IGNORECASE)
    depth = 1
    for token_match in token_pattern.finditer(text, start_index):
        token = token_match.group(0).lower()
        if token == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return token_match.start()
    return None


def block_drives_any_signal(block_text: str, signal_names: list[str]) -> bool:
    """Return True when a block appears to assign at least one named signal."""

    for signal_name in signal_names:
        if re.search(rf"(?m)\b{re.escape(signal_name)}\s*(?:<=|=)\s*", block_text):
            return True
    return False


def is_clock_generation_block(block_text: str, clock_name: str) -> bool:
    """Return True for an obvious dedicated clock-generation process."""

    normalized = " ".join(block_text.lower().split())
    if "forever" not in normalized and "#" not in normalized:
        return False
    return bool(
        re.search(
            rf"\b{re.escape(clock_name.lower())}\s*(?:<=|=)\s*~\s*{re.escape(clock_name.lower())}\b",
            normalized,
        )
    )
