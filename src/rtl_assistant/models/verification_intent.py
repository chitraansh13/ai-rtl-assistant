import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from rtl_assistant.models.hardware_spec import DesignType
from rtl_assistant.models.verification_common import TestCategory


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
INTENT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TOKEN_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _validate_non_empty_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    return stripped


def _normalize_token(value: str, field_name: str) -> str:
    normalized = _validate_non_empty_text(value, field_name).upper().replace("-", "_").replace(" ", "_")
    if not TOKEN_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must be an uppercase semantic token")
    return normalized


class PreconditionIntent(BaseModel):
    """Structured, non-executable precondition requested by AI intent."""

    kind: str
    signal: str | None = None
    value: int | str | bool | None = None
    description: str | None = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        return _normalize_token(value, "Precondition kind")

    @field_validator("signal")
    @classmethod
    def validate_signal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = _validate_non_empty_text(value, "Precondition signal")
        if not IDENTIFIER_PATTERN.fullmatch(stripped):
            raise ValueError("Precondition signal must be a valid identifier")
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_non_empty_text(value, "Precondition description")


class VerificationIntentCase(BaseModel):
    """AI-facing verification intent without executable timing prose."""

    id: str
    name: str
    category: TestCategory
    target_behavior: str
    scenario: str
    priority: int = Field(..., ge=1, le=3)
    vector_hints: dict[str, int | str | bool] = Field(default_factory=dict)
    precondition_intent: PreconditionIntent | None = None
    edge_count_hint: int | None = Field(None, ge=1)
    coverage_tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        stripped = _validate_non_empty_text(value, "Intent-case id")
        if not INTENT_ID_PATTERN.fullmatch(stripped):
            raise ValueError("Intent-case id must use lowercase snake_case")
        return stripped

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_non_empty_text(value, "Intent-case name")

    @field_validator("target_behavior")
    @classmethod
    def validate_behavior(cls, value: str) -> str:
        return _normalize_token(value, "Target behavior")

    @field_validator("scenario")
    @classmethod
    def validate_scenario(cls, value: str) -> str:
        return _normalize_token(value, "Scenario")

    @field_validator("vector_hints")
    @classmethod
    def validate_vector_hints(cls, value: dict[str, Any]) -> dict[str, int | str | bool]:
        normalized: dict[str, int | str | bool] = {}
        for key, hint_value in value.items():
            signal_name = _validate_non_empty_text(str(key), "Vector-hint signal")
            if not IDENTIFIER_PATTERN.fullmatch(signal_name):
                raise ValueError("Vector-hint keys must be valid identifiers")
            if not isinstance(hint_value, (int, str, bool)):
                raise ValueError("Vector hints must use only int, str, or bool values")
            normalized[signal_name] = hint_value
        return normalized

    @field_validator("coverage_tags", "notes")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class VerificationIntentPlan(BaseModel):
    """AI-facing verification intent that remains above the deterministic trust boundary."""

    schema_version: str = "2.0"
    module_name: str
    design_type: DesignType
    strategy: str
    cases: list[VerificationIntentCase]
    coverage_targets: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, value: str) -> str:
        stripped = _validate_non_empty_text(value, "Module name")
        if not IDENTIFIER_PATTERN.fullmatch(stripped):
            raise ValueError("module_name must be a valid simple SystemVerilog-style identifier")
        return stripped

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        return _validate_non_empty_text(value, "Strategy")

    @field_validator("coverage_targets", "assumptions", "notes")
    @classmethod
    def validate_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_invariants(self) -> "VerificationIntentPlan":
        if not self.cases:
            raise ValueError("VerificationIntentPlan must define at least one intent case")

        case_ids = [case.id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("VerificationIntentPlan contains duplicate case ids")

        return self
