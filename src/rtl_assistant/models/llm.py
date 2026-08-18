from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from rtl_assistant.models.hardware_spec import HardwareSpec


class LLMStatus(str, Enum):
    """Enumeration of LLM request outcome states."""

    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class RequirementStatus(str, Enum):
    """Enumeration of requirement parsing outcomes."""

    READY = "READY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    FAIL = "FAIL"


class LLMResponse(BaseModel):
    """Structured result returned by an LLM provider."""

    provider: str
    model: str
    prompt: str
    response_text: str
    success: bool
    status: LLMStatus
    duration_ms: int | None = Field(None, ge=0)
    error_type: str | None = None
    error_message: str | None = None
    raw_response: dict | None = None
    prompt_tokens: int | None = Field(None, ge=0)
    completion_tokens: int | None = Field(None, ge=0)
    total_duration_ns: int | None = Field(None, ge=0)

    @field_validator("provider", "model", "prompt")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped

    @model_validator(mode="after")
    def validate_invariants(self) -> "LLMResponse":
        """Enforce consistency between success flags and metadata."""

        if self.status == LLMStatus.SUCCESS:
            if not self.success:
                raise ValueError("status 'SUCCESS' requires success to be True")
            if not self.response_text.strip():
                raise ValueError("Successful response_text cannot be empty")
            if self.error_type is not None:
                raise ValueError("status 'SUCCESS' requires error_type to be None")

        if self.status == LLMStatus.FAIL and self.success:
            raise ValueError("status 'FAIL' requires success to be False")

        return self


class ClarificationQuestion(BaseModel):
    """A structured clarification request for missing critical hardware details."""

    id: str
    field: str
    question: str
    reason: str
    required: bool = True
    choices: list[str] = Field(default_factory=list)
    default: str | None = None

    @field_validator("id", "field", "question", "reason")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be empty")
        return stripped


class RequirementAnalysis(BaseModel):
    """Structured ambiguity analysis over the original user requirement."""

    ready: bool
    explicitly_specified: list[str] = Field(default_factory=list)
    safely_inferred: list[str] = Field(default_factory=list)
    missing_critical: list[str] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_invariants(self) -> "RequirementAnalysis":
        """Ensure ready state aligns with missing critical information."""

        if self.ready:
            if self.missing_critical:
                raise ValueError("ready=True requires missing_critical to be empty")
            if self.clarification_questions:
                raise ValueError("ready=True requires clarification_questions to be empty")
        else:
            if not self.missing_critical and not self.clarification_questions and not self.ambiguous:
                raise ValueError(
                    "ready=False requires missing_critical, ambiguous items, or clarification_questions"
                )

        return self


class RequirementParseResult(BaseModel):
    """Structured outcome of parsing a natural-language requirement into a HardwareSpec."""

    requirement: str
    status: RequirementStatus
    hardware_spec: HardwareSpec | None = None
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    raw_model_output: str = ""
    provider: str | None = None
    model: str | None = None
    attempts: int = Field(..., ge=1)
    validation_errors: list[str] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: int | None = Field(None, ge=0)

    @field_validator("requirement")
    @classmethod
    def validate_requirement(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Requirement cannot be empty")
        return stripped

    @model_validator(mode="after")
    def validate_invariants(self) -> "RequirementParseResult":
        """Ensure status-specific result fields remain coherent."""

        if self.status == RequirementStatus.READY:
            if self.hardware_spec is None:
                raise ValueError("READY result requires a non-null hardware_spec")
            if self.clarification_questions:
                raise ValueError("READY result requires clarification_questions to be empty")
            if self.unresolved_fields:
                raise ValueError("READY result requires unresolved_fields to be empty")
            if self.error_type is not None:
                raise ValueError("READY result requires error_type to be None")
            if self.provider is None or self.model is None:
                raise ValueError("READY result requires provider and model metadata")

        if self.status == RequirementStatus.NEEDS_CLARIFICATION:
            if not self.clarification_questions:
                raise ValueError("NEEDS_CLARIFICATION result requires clarification_questions")
            if self.error_type is not None:
                raise ValueError("NEEDS_CLARIFICATION result cannot contain provider/infrastructure failure")

        if self.status == RequirementStatus.FAIL:
            if self.hardware_spec is not None:
                raise ValueError("FAIL result cannot include an approved final hardware_spec")

        return self
