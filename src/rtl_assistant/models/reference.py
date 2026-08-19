from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class ReferenceResolutionStatus(str, Enum):
    """Enumeration of deterministic reference-resolution outcomes."""

    RESOLVED = "RESOLVED"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"


class ReferenceResolution(BaseModel):
    """Structured outcome of resolving expected values for one test case."""

    status: ReferenceResolutionStatus
    resolver: str
    expected_values: dict[str, int | str] = Field(default_factory=dict)
    canonical_expected: list[str] = Field(default_factory=list)
    explanation: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    @field_validator("resolver")
    @classmethod
    def validate_resolver(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("resolver cannot be empty")
        return stripped

    @field_validator("canonical_expected")
    @classmethod
    def validate_canonical_expected(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_invariants(self) -> "ReferenceResolution":
        """Keep resolution state consistent with payload presence."""

        if self.status == ReferenceResolutionStatus.RESOLVED:
            if not self.expected_values:
                raise ValueError("RESOLVED reference result requires expected_values")
            if not self.canonical_expected:
                raise ValueError("RESOLVED reference result requires canonical_expected")
            if self.error_type is not None:
                raise ValueError("RESOLVED reference result requires error_type to be None")

        if self.status == ReferenceResolutionStatus.UNSUPPORTED and self.error_type is not None:
            raise ValueError("UNSUPPORTED reference result cannot carry error_type")

        if self.status == ReferenceResolutionStatus.ERROR:
            if self.error_type is None:
                raise ValueError("ERROR reference result requires error_type")

        return self


class ReferenceCorrection(BaseModel):
    """Record one deterministic correction made to AI-proposed expected values."""

    test_case_id: str
    resolver: str
    ai_expected: list[str] = Field(default_factory=list)
    deterministic_expected: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @field_validator("test_case_id", "resolver")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @field_validator("ai_expected", "deterministic_expected")
    @classmethod
    def validate_expected_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def validate_invariants(self) -> "ReferenceCorrection":
        """Require both sides of the correction trail to remain visible."""

        if not self.ai_expected:
            raise ValueError("ReferenceCorrection requires ai_expected")
        if not self.deterministic_expected:
            raise ValueError("ReferenceCorrection requires deterministic_expected")
        return self
