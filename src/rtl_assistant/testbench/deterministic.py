import re
import time

from rtl_assistant.models.hardware_spec import DesignType, HardwareSpec
from rtl_assistant.models.testbench_generation import (
    TestbenchGenerationMode,
    TestbenchGenerationResult,
    TestbenchGenerationStatus,
)
from rtl_assistant.models.verification_plan import VerificationPlan
from rtl_assistant.testbench.ir import TestbenchPlan
from rtl_assistant.testbench.renderer import render_testbench
from rtl_assistant.testbench.translator import (
    TestbenchTranslationError,
    translate_verification_plan,
)


FORBIDDEN_DUT_REDEFINITION_TEMPLATE = "DUT_REDEFINED: Generated testbench redefines the DUT module '{module_name}'."


class DeterministicTestbenchGenerator:
    """Deterministically translate and render a SystemVerilog testbench from structured inputs."""

    def generate(
        self,
        hardware_spec: HardwareSpec,
        verification_plan: VerificationPlan,
    ) -> TestbenchGenerationResult:
        """Translate, render, and validate a deterministic testbench."""

        started_at = time.perf_counter()

        try:
            testbench_plan = translate_verification_plan(hardware_spec, verification_plan)
        except TestbenchTranslationError as exc:
            return self._failure_result(
                hardware_spec=hardware_spec,
                started_at=started_at,
                test_count=len(verification_plan.test_cases),
                error_type=exc.error_type,
                errors=[f"{exc.error_type}: {exc.message}"],
            )

        try:
            testbench_text = render_testbench(hardware_spec, testbench_plan)
        except ValueError as exc:
            return self._failure_result(
                hardware_spec=hardware_spec,
                started_at=started_at,
                test_count=len(testbench_plan.tests),
                error_type="TESTBENCH_RENDER_ERROR",
                errors=[f"TESTBENCH_RENDER_ERROR: {exc}"],
            )

        errors = run_testbench_sanity_checks(hardware_spec, verification_plan, testbench_text)
        if errors:
            return self._failure_result(
                hardware_spec=hardware_spec,
                started_at=started_at,
                test_count=len(testbench_plan.tests),
                error_type=derive_primary_error_type(errors),
                errors=errors,
            )

        return TestbenchGenerationResult(
            status=TestbenchGenerationStatus.SUCCESS,
            generation_mode=TestbenchGenerationMode.DETERMINISTIC,
            module_name=hardware_spec.module_name,
            testbench_text=testbench_text,
            provider=None,
            model=None,
            prompt_version=None,
            attempts=1,
            test_count=len(testbench_plan.tests),
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            raw_response=None,
            error_type=None,
            error_message=None,
            validation_errors=[],
        )

    def _failure_result(
        self,
        hardware_spec: HardwareSpec,
        started_at: float,
        test_count: int,
        error_type: str,
        errors: list[str],
    ) -> TestbenchGenerationResult:
        """Build one deterministic failure result."""

        return TestbenchGenerationResult(
            status=TestbenchGenerationStatus.FAIL,
            generation_mode=TestbenchGenerationMode.DETERMINISTIC,
            module_name=hardware_spec.module_name,
            testbench_text=None,
            provider=None,
            model=None,
            prompt_version=None,
            attempts=1,
            test_count=test_count,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            raw_response=None,
            error_type=error_type,
            error_message=errors[0] if errors else "Deterministic testbench generation failed.",
            validation_errors=errors,
        )


def run_testbench_sanity_checks(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    testbench_text: str,
) -> list[str]:
    """Run lightweight deterministic checks on rendered testbench text."""

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
    errors.extend(validate_stimulus_process_structure(hardware_spec, testbench_text))
    errors.extend(validate_clock_and_reset_usage(hardware_spec, testbench_text))
    errors.extend(validate_finish_and_self_checking(testbench_text))

    return errors


def find_dut_instantiation(dut_module_name: str, text: str) -> re.Match[str] | None:
    """Find a plausible DUT instantiation."""

    pattern = re.compile(
        rf"\b{re.escape(dut_module_name)}\b\s+(?:#\s*\(.*?\)\s*)?([A-Za-z_][A-Za-z0-9_$]*)\s*\((.*?)\)\s*;",
        re.DOTALL,
    )
    return pattern.search(text)


def validate_output_ports_not_driven(hardware_spec: HardwareSpec, testbench_text: str) -> list[str]:
    """Reject obvious writes to DUT output-connected testbench signals."""

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
    """Require every VerificationPlan test-case id to appear in the testbench."""

    missing_ids = [test_case.id for test_case in verification_plan.test_cases if test_case.id not in testbench_text]
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
    """Require inline comparison evidence for each planned expected output."""

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


def validate_stimulus_process_structure(
    hardware_spec: HardwareSpec,
    testbench_text: str,
) -> list[str]:
    """Reject multiple concurrent DUT-driving initial blocks."""

    input_names = [port.name for port in hardware_spec.ports if port.direction.value == "input"]
    initial_bodies = extract_initial_block_bodies(testbench_text)
    if len(initial_bodies) <= 1 or not input_names:
        return []

    stimulus_blocks = [body for body in initial_bodies if block_drives_any_signal(body, input_names)]
    if len(stimulus_blocks) <= 1:
        return []

    if hardware_spec.design_type == DesignType.SEQUENTIAL and hardware_spec.clock is not None:
        non_clock_blocks = [
            body for body in stimulus_blocks if not is_clock_generation_block(body, hardware_spec.clock.signal)
        ]
        if len(non_clock_blocks) <= 1:
            return []

    return [
        "MULTIPLE_STIMULUS_PROCESSES: Generated testbench appears to contain multiple concurrent initial blocks driving DUT input signals."
    ]


def validate_clock_and_reset_usage(hardware_spec: HardwareSpec, testbench_text: str) -> list[str]:
    """Check basic sequential clock/reset infrastructure requirements."""

    errors: list[str] = []
    if hardware_spec.design_type == DesignType.SEQUENTIAL:
        if hardware_spec.clock is None:
            errors.append("CLOCK_GENERATION_MISSING: Sequential HardwareSpec is missing clock metadata.")
            return errors

        clock_name = hardware_spec.clock.signal
        has_clock_logic = (
            re.search(rf"\bforever\b[\s\S]*?\b{re.escape(clock_name)}\s*=\s*~\s*{re.escape(clock_name)}\b", testbench_text)
            or re.search(rf"\balways\b[\s\S]*?\b{re.escape(clock_name)}\s*=\s*~\s*{re.escape(clock_name)}\b", testbench_text)
        )
        if not has_clock_logic:
            errors.append(
                f"CLOCK_GENERATION_MISSING: Sequential testbench does not clearly generate or toggle clock '{clock_name}'."
            )

        if hardware_spec.reset is not None and hardware_spec.reset.signal not in testbench_text:
            errors.append(
                f"RESET_REFERENCE_MISSING: Generated testbench does not clearly reference reset signal '{hardware_spec.reset.signal}'."
            )

    return errors


def validate_finish_and_self_checking(testbench_text: str) -> list[str]:
    """Check for deterministic footer and self-checking behavior."""

    errors: list[str] = []
    if "$finish" not in testbench_text:
        errors.append("MISSING_FINISH: Generated testbench does not contain $finish.")

    has_comparison = any(operator in testbench_text for operator in ("!==", "===", "!=", "=="))
    has_pass_fail_text = any(marker in testbench_text for marker in ("PASS", "failed_tests"))
    if not has_comparison or not has_pass_fail_text:
        errors.append(
            "SELF_CHECKING_MISSING: Generated testbench does not clearly contain self-checking PASS/FAIL comparison logic."
        )

    if not re.search(r"\bfailed_tests\b", testbench_text):
        errors.append(
            "FAILURE_COUNT_MISSING: Generated testbench does not clearly maintain a failed_tests counter."
        )

    has_final_summary = re.search(r'(?i)\$display\s*\(\s*"[^"]*failed tests[^"]*"', testbench_text)
    has_all_passed = "ALL TESTS PASSED" in testbench_text
    if not has_final_summary or not has_all_passed:
        errors.append(
            "MISSING_FINAL_SUMMARY: Generated testbench does not clearly print the deterministic final summary."
        )

    return errors


def derive_primary_error_type(errors: list[str]) -> str:
    """Extract a primary structured error type from a list of validation errors."""

    if not errors:
        return "TESTBENCH_RENDER_ERROR"
    return errors[0].split(":", 1)[0].strip() or "TESTBENCH_RENDER_ERROR"


def extract_expected_output_names(expected_items: list[str], output_names: list[str]) -> list[str]:
    """Return output names explicitly represented in one test's expected list."""

    matched_outputs: list[str] = []
    combined_expected = "\n".join(expected_items)
    for output_name in output_names:
        if re.search(rf"\b{re.escape(output_name)}\b", combined_expected):
            matched_outputs.append(output_name)
    return matched_outputs


def extract_test_region(testbench_text: str, test_id: str, following_ids: list[str]) -> str | None:
    """Extract one test's approximate inline implementation region."""

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


def has_output_comparison(test_region: str, output_name: str) -> bool:
    """Return True when one output appears in a real comparison expression."""

    return bool(
        re.search(rf"\b{re.escape(output_name)}\b\s*(?:!==|!=|===|==)", test_region)
        or re.search(rf"(?:!==|!=|===|==)\s*\b{re.escape(output_name)}\b", test_region)
    )


def extract_initial_block_bodies(testbench_text: str) -> list[str]:
    """Extract initial-block bodies with a lightweight token matcher."""

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
    """Find the end of a begin/end block using shallow token counting."""

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
    """Return True when a block appears to assign one named signal."""

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
