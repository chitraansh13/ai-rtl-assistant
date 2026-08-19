from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from rtl_assistant.models.hardware_spec import DesignType


class TestbenchActionType(str, Enum):
    """Enumeration of deterministic testbench action kinds."""

    SET_INPUT = "set_input"
    ACTIVE_CLOCK_EDGE = "active_clock_edge"
    REPEAT_ACTIVE_EDGES = "repeat_active_edges"
    SETTLE = "settle"


class InputAssignment(BaseModel):
    """Deterministic assignment to one DUT input signal."""

    signal: str
    value: int = Field(..., ge=0)

    @field_validator("signal")
    @classmethod
    def validate_signal(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("signal cannot be empty")
        return stripped


class ExpectedCheck(BaseModel):
    """One deterministic expected DUT-output comparison."""

    signal: str
    value: int | None = Field(None, ge=0)
    reference_signal: str | None = None

    @field_validator("signal", "reference_signal")
    @classmethod
    def validate_signal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("signal cannot be empty")
        return stripped

    @model_validator(mode="after")
    def validate_invariants(self) -> "ExpectedCheck":
        """Require exactly one expected-check form."""

        if self.value is None and self.reference_signal is None:
            raise ValueError("ExpectedCheck requires either value or reference_signal")
        if self.value is not None and self.reference_signal is not None:
            raise ValueError("ExpectedCheck must not define both value and reference_signal")
        return self


class TestbenchAction(BaseModel):
    """One executable deterministic testbench action."""

    type: TestbenchActionType
    assignment: InputAssignment | None = None
    count: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def validate_invariants(self) -> "TestbenchAction":
        """Keep action payload consistent with the action type."""

        if self.type == TestbenchActionType.SET_INPUT:
            if self.assignment is None:
                raise ValueError("SET_INPUT action requires assignment")
            if self.count is not None:
                raise ValueError("SET_INPUT action must not include count")

        if self.type == TestbenchActionType.ACTIVE_CLOCK_EDGE:
            if self.assignment is not None:
                raise ValueError("ACTIVE_CLOCK_EDGE action must not include assignment")
            if self.count is not None:
                raise ValueError("ACTIVE_CLOCK_EDGE action must not include count")

        if self.type == TestbenchActionType.REPEAT_ACTIVE_EDGES:
            if self.assignment is not None:
                raise ValueError("REPEAT_ACTIVE_EDGES action must not include assignment")
            if self.count is None:
                raise ValueError("REPEAT_ACTIVE_EDGES action requires count")

        if self.type == TestbenchActionType.SETTLE:
            if self.assignment is not None or self.count is not None:
                raise ValueError("SETTLE action must not include assignment or count")

        return self


class TestbenchCase(BaseModel):
    """Executable deterministic form of one verification-plan test case."""

    id: str
    name: str
    actions: list[TestbenchAction]
    checks: list[ExpectedCheck]

    @field_validator("id", "name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @model_validator(mode="after")
    def validate_invariants(self) -> "TestbenchCase":
        """Require each executable case to have actions and checks."""

        if not self.actions:
            raise ValueError("TestbenchCase must define at least one action")
        if not self.checks:
            raise ValueError("TestbenchCase must define at least one expected check")
        return self


class TestbenchPlan(BaseModel):
    """Deterministic executable testbench plan derived from HardwareSpec and VerificationPlan."""

    module_name: str
    design_type: DesignType
    tests: list[TestbenchCase]

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("module_name cannot be empty")
        return stripped

    @model_validator(mode="after")
    def validate_invariants(self) -> "TestbenchPlan":
        """Require at least one executable test."""

        if not self.tests:
            raise ValueError("TestbenchPlan must define at least one test")
        return self
