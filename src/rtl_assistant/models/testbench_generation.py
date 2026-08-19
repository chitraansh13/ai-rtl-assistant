import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class TestbenchGenerationStatus(str, Enum):
    """Enumeration of testbench-generation outcomes."""

    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class TestbenchGenerationMode(str, Enum):
    """Enumeration of testbench-generation implementation modes."""

    DETERMINISTIC = "deterministic"
    AI = "ai"


class TestbenchGenerationResult(BaseModel):
    """Structured outcome of generating a SystemVerilog testbench."""

    status: TestbenchGenerationStatus
    generation_mode: TestbenchGenerationMode
    module_name: str
    testbench_text: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    attempts: int = Field(..., ge=1)
    test_count: int | None = Field(None, ge=0)
    duration_ms: int | None = Field(None, ge=0)
    raw_response: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    validation_errors: list[str] = Field(default_factory=list)

    @field_validator("module_name")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @field_validator("provider", "model", "prompt_version")
    @classmethod
    def validate_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
    def validate_invariants(self) -> "TestbenchGenerationResult":
        """Enforce consistency between status, testbench text, and errors."""

        if self.status == TestbenchGenerationStatus.SUCCESS:
            if self.testbench_text is None or not self.testbench_text.strip():
                raise ValueError("SUCCESS result requires non-empty testbench_text")
            if self.error_type is not None:
                raise ValueError("SUCCESS result requires error_type to be None")
            if self.error_message is not None:
                raise ValueError("SUCCESS result requires error_message to be None")
            if self.validation_errors:
                raise ValueError("SUCCESS result requires validation_errors to be empty")

        if self.status == TestbenchGenerationStatus.FAIL and self.testbench_text is not None and not self.testbench_text.strip():
            self.testbench_text = None

        if self.generation_mode == TestbenchGenerationMode.DETERMINISTIC:
            if self.provider is not None or self.model is not None or self.prompt_version is not None:
                raise ValueError("Deterministic generation must not fake provider/model/prompt metadata")
            if self.raw_response is not None:
                raise ValueError("Deterministic generation must not include raw_response")

        if self.generation_mode == TestbenchGenerationMode.AI:
            if self.provider is None or self.model is None or self.prompt_version is None:
                raise ValueError("AI generation requires provider, model, and prompt_version metadata")

        return self
