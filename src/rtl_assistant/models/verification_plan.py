import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from rtl_assistant.models.hardware_spec import DesignType
from rtl_assistant.models.reference import ReferenceCorrection


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
TEST_CASE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class VerificationPlanStatus(str, Enum):
    """Enumeration of verification-plan generation outcomes."""

    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class TestCategory(str, Enum):
    """High-level verification test categories."""

    BASIC = "BASIC"
    FUNCTIONAL = "FUNCTIONAL"
    RESET = "RESET"
    CONTROL = "CONTROL"
    EDGE_CASE = "EDGE_CASE"
    BOUNDARY = "BOUNDARY"
    STATE_TRANSITION = "STATE_TRANSITION"
    ARITHMETIC = "ARITHMETIC"
    INVALID_OR_GUARDED = "INVALID_OR_GUARDED"
    OTHER = "OTHER"


def validate_non_empty_text(value: str, field_name: str) -> str:
    """Normalize and validate a required text field."""

    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    return stripped


class VerificationTestCase(BaseModel):
    """Structured test intent for one verification scenario."""

    id: str
    name: str
    category: TestCategory
    description: str
    setup: list[str] = Field(default_factory=list)
    stimulus: list[str] = Field(default_factory=list)
    expected: list[str]
    covers: list[str] = Field(default_factory=list)
    priority: int = Field(..., ge=1, le=3)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        stripped = validate_non_empty_text(value, "Test-case id")
        if not TEST_CASE_ID_PATTERN.fullmatch(stripped):
            raise ValueError("Test-case id must use lowercase snake_case")
        return stripped

    @field_validator("name", "description")
    @classmethod
    def validate_required_text(cls, value: str, info) -> str:
        return validate_non_empty_text(value, info.field_name.replace("_", " ").title())

    @field_validator("setup", "stimulus", "expected", "covers")
    @classmethod
    def validate_string_lists(cls, value: list[str], info) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            stripped = item.strip()
            if stripped:
                cleaned.append(stripped)
        if info.field_name == "expected" and not cleaned:
            raise ValueError("Each test case must define at least one expected outcome")
        return cleaned


class VerificationPlan(BaseModel):
    """Validated structured verification intent derived from a HardwareSpec."""

    schema_version: str = "1.0"
    module_name: str
    design_type: DesignType
    strategy: str
    test_cases: list[VerificationTestCase]
    coverage_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("module_name", "strategy")
    @classmethod
    def validate_required_strings(cls, value: str, info) -> str:
        stripped = validate_non_empty_text(value, info.field_name.replace("_", " ").title())
        if info.field_name == "module_name" and not IDENTIFIER_PATTERN.fullmatch(stripped):
            raise ValueError("module_name must be a valid simple SystemVerilog-style identifier")
        return stripped

    @field_validator("coverage_targets", "assumptions", "notes")
    @classmethod
    def validate_non_empty_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_invariants(self) -> "VerificationPlan":
        """Enforce plan-level consistency."""

        if not self.test_cases:
            raise ValueError("VerificationPlan must define at least one test case")

        test_ids = [test_case.id for test_case in self.test_cases]
        if len(set(test_ids)) != len(test_ids):
            raise ValueError("VerificationPlan contains duplicate test-case ids")

        return self


class VerificationPlanGenerationResult(BaseModel):
    """Structured outcome of generating a verification plan from a HardwareSpec."""

    status: VerificationPlanStatus
    module_name: str
    verification_plan: VerificationPlan | None = None
    provider: str
    model: str
    prompt_version: str
    attempts: int = Field(..., ge=1)
    duration_ms: int | None = Field(None, ge=0)
    raw_model_output: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    reference_corrections: list[ReferenceCorrection] = Field(default_factory=list)

    @field_validator("module_name", "provider", "model", "prompt_version")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, value: str) -> str:
        if not IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError("module_name must be a valid simple SystemVerilog-style identifier")
        return value

    @model_validator(mode="after")
    def validate_invariants(self) -> "VerificationPlanGenerationResult":
        """Enforce consistency between status, plan presence, and errors."""

        if self.status == VerificationPlanStatus.SUCCESS:
            if self.verification_plan is None:
                raise ValueError("SUCCESS result requires a validated verification_plan")
            if self.error_type is not None:
                raise ValueError("SUCCESS result requires error_type to be None")
            if self.error_message is not None:
                raise ValueError("SUCCESS result requires error_message to be None")
            if self.validation_errors:
                raise ValueError("SUCCESS result requires validation_errors to be empty")

        if self.status == VerificationPlanStatus.FAIL and self.verification_plan is not None:
            raise ValueError("FAIL result cannot include an approved verification_plan")

        return self
