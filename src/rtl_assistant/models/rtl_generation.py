import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class RTLGenerationStatus(str, Enum):
    """Enumeration of RTL generation outcomes."""

    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class RTLGenerationResult(BaseModel):
    """Structured outcome of generating SystemVerilog RTL from a validated HardwareSpec."""

    status: RTLGenerationStatus
    module_name: str
    rtl: str | None = None
    provider: str
    model: str
    prompt_version: str
    attempts: int = Field(..., ge=1)
    duration_ms: int | None = Field(None, ge=0)
    raw_model_output: str | None = None
    error_type: str | None = None
    error_message: str | None = None

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
    def validate_invariants(self) -> "RTLGenerationResult":
        """Enforce consistency between status, RTL text, and error metadata."""

        if self.status == RTLGenerationStatus.SUCCESS:
            if self.rtl is None or not self.rtl.strip():
                raise ValueError("SUCCESS result requires non-empty RTL text")
            if self.error_type is not None:
                raise ValueError("SUCCESS result requires error_type to be None")

        if self.status == RTLGenerationStatus.FAIL:
            if self.rtl is not None and not self.rtl.strip():
                self.rtl = None

        return self
