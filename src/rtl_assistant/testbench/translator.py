from rtl_assistant.models.compiled_verification_plan import (
    CompiledVerificationCase,
    CompiledVerificationPlan,
)
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.testbench.ir import TestbenchCase, TestbenchPlan


class TestbenchTranslationError(Exception):
    """Structured deterministic-translation failure."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(f"{error_type}: {message}")
        self.error_type = error_type
        self.message = message


def translate_verification_plan(
    hardware_spec: HardwareSpec,
    compiled_plan: CompiledVerificationPlan,
) -> TestbenchPlan:
    """Translate a compiled verification plan directly into executable testbench IR."""

    if compiled_plan.module_name != hardware_spec.module_name:
        raise TestbenchTranslationError(
            "MODULE_NAME_MISMATCH",
            f"Compiled plan targets '{compiled_plan.module_name}' but HardwareSpec defines '{hardware_spec.module_name}'.",
        )

    translated_cases = [translate_compiled_case(test_case) for test_case in compiled_plan.cases]
    return TestbenchPlan(
        module_name=compiled_plan.module_name,
        design_type=compiled_plan.design_type,
        tests=translated_cases,
    )


def translate_compiled_case(test_case: CompiledVerificationCase) -> TestbenchCase:
    """Translate one compiled verification case into the renderer-facing IR."""

    return TestbenchCase(
        id=test_case.id,
        name=test_case.name,
        actions=test_case.actions,
        checks=test_case.checks,
    )
