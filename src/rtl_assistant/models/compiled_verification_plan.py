from pydantic import BaseModel, Field, field_validator, model_validator

from rtl_assistant.models.hardware_spec import DesignType
from rtl_assistant.models.verification_common import TestCategory
from rtl_assistant.testbench.ir import ExpectedCheck, TestbenchAction


class CompiledVerificationCase(BaseModel):
    """Deterministically compiled executable verification semantics for one case."""

    id: str
    name: str
    category: TestCategory
    target_behavior: str
    scenario: str
    priority: int = Field(..., ge=1, le=3)
    actions: list[TestbenchAction]
    checks: list[ExpectedCheck]
    coverage_tags: list[str] = Field(default_factory=list)
    state_provenance: list[str] = Field(default_factory=list)
    compilation_notes: list[str] = Field(default_factory=list)

    @field_validator("id", "name", "target_behavior", "scenario")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @field_validator("coverage_tags", "state_provenance", "compilation_notes")
    @classmethod
    def validate_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_invariants(self) -> "CompiledVerificationCase":
        if not self.actions:
            raise ValueError("CompiledVerificationCase must define at least one action")
        if not self.checks:
            raise ValueError("CompiledVerificationCase must define at least one expected check")
        return self


class CompiledVerificationPlan(BaseModel):
    """Executable compiled verification plan produced deterministically from AI intent."""

    schema_version: str = "2.0"
    module_name: str
    design_type: DesignType
    strategy: str
    cases: list[CompiledVerificationCase]
    coverage_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("module_name", "strategy")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @field_validator("coverage_targets", "assumptions", "notes")
    @classmethod
    def validate_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_invariants(self) -> "CompiledVerificationPlan":
        if not self.cases:
            raise ValueError("CompiledVerificationPlan must define at least one compiled case")

        case_ids = [case.id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("CompiledVerificationPlan contains duplicate case ids")

        return self
