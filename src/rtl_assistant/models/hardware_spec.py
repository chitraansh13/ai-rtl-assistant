from enum import Enum
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from rtl_assistant.models.semantic_feature import SemanticFeature
from rtl_assistant.models.semantics import HardwareSemantics, SemanticConstraints


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class LowercaseStrEnum(str, Enum):
    """Base enum that serializes to readable lowercase JSON strings."""

    def _generate_next_value_(name: str, start: int, count: int, last_values: list[object]) -> str:
        return name.lower()


class DesignType(LowercaseStrEnum):
    COMBINATIONAL = "combinational"
    SEQUENTIAL = "sequential"


class PortDirection(LowercaseStrEnum):
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


class PortRole(LowercaseStrEnum):
    DATA = "data"
    CLOCK = "clock"
    RESET = "reset"
    CONTROL = "control"
    STATUS = "status"
    OTHER = "other"


class ClockEdge(LowercaseStrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class ResetType(LowercaseStrEnum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


class ResetPolarity(LowercaseStrEnum):
    ACTIVE_HIGH = "active_high"
    ACTIVE_LOW = "active_low"


def is_valid_identifier(value: str) -> bool:
    """Return True for a simple SystemVerilog-style identifier."""

    return bool(IDENTIFIER_PATTERN.fullmatch(value))


def validate_identifier(value: str, field_name: str) -> str:
    """Validate and normalize an identifier-like field."""

    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} cannot be empty")
    if not is_valid_identifier(stripped):
        raise ValueError(f"{field_name} must be a valid simple SystemVerilog-style identifier")
    return stripped


class PortSpec(BaseModel):
    """Structured specification for one module port."""

    name: str
    direction: PortDirection
    width: int = Field(1, ge=1)
    signed: bool = False
    role: PortRole = PortRole.DATA
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_identifier(value, "Port name")


class ParameterSpec(BaseModel):
    """Structured specification for one module parameter."""

    name: str
    default: int | str | bool
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_identifier(value, "Parameter name")


class ClockSpec(BaseModel):
    """Clocking information for sequential hardware designs."""

    signal: str
    edge: ClockEdge
    frequency_hz: float | None = Field(None, gt=0)

    @field_validator("signal")
    @classmethod
    def validate_signal(cls, value: str) -> str:
        return validate_identifier(value, "Clock signal")


class ResetSpec(BaseModel):
    """Reset information for hardware designs."""

    signal: str
    type: ResetType
    polarity: ResetPolarity
    priority: str | None = None
    reset_values: dict[str, int | str] = Field(default_factory=dict)

    @field_validator("signal")
    @classmethod
    def validate_signal(cls, value: str) -> str:
        return validate_identifier(value, "Reset signal")


class BehaviorSpec(BaseModel):
    """Structured but flexible behavioral description."""

    description: str = "High-level behavior metadata omitted."
    operations: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Behavior description cannot be empty")
        return stripped


class HardwareSpec(BaseModel):
    """Validated, reusable hardware design specification."""

    schema_version: str = "1.0"
    module_name: str
    design_type: DesignType
    description: str | None = None
    parameters: list[ParameterSpec] = Field(default_factory=list)
    ports: list[PortSpec]
    clock: ClockSpec | None = None
    reset: ResetSpec | None = None
    semantics: HardwareSemantics | None = None
    semantic_features: list[SemanticFeature] = Field(default_factory=list)
    semantic_constraints: SemanticConstraints | None = None
    behavior: BehaviorSpec
    tags: list[str] = Field(default_factory=list)

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, value: str) -> str:
        return validate_identifier(value, "Module name")

    @model_validator(mode="after")
    def validate_cross_fields(self) -> "HardwareSpec":
        """Validate cross-field consistency across ports, clocking, and reset."""

        if not self.ports:
            raise ValueError("HardwareSpec must define at least one port")

        port_names = [port.name for port in self.ports]
        if len(set(port_names)) != len(port_names):
            raise ValueError("HardwareSpec contains duplicate port names")

        parameter_names = [parameter.name for parameter in self.parameters]
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("HardwareSpec contains duplicate parameter names")

        ports_by_name = {port.name: port for port in self.ports}

        if self.design_type == DesignType.SEQUENTIAL and self.clock is None:
            raise ValueError("Sequential designs must define a ClockSpec")

        if self.design_type == DesignType.COMBINATIONAL and self.clock is not None:
            raise ValueError("Combinational designs should not define a ClockSpec in this first version")

        if self.design_type == DesignType.COMBINATIONAL and self.reset is not None:
            raise ValueError("Combinational designs should not define a ResetSpec in this first version")

        if self.clock is not None:
            if self.clock.signal not in ports_by_name:
                raise ValueError(f"Clock signal '{self.clock.signal}' does not match any declared port")
            clock_port = ports_by_name[self.clock.signal]
            if clock_port.direction != PortDirection.INPUT:
                raise ValueError(f"Clock signal '{self.clock.signal}' must refer to an input port")
            if clock_port.width != 1:
                raise ValueError(f"Clock signal '{self.clock.signal}' must be 1 bit wide")
            if clock_port.role != PortRole.CLOCK:
                raise ValueError(f"Clock signal '{self.clock.signal}' must use role 'clock'")

        if self.reset is not None:
            if self.reset.signal not in ports_by_name:
                raise ValueError(f"Reset signal '{self.reset.signal}' does not match any declared port")
            reset_port = ports_by_name[self.reset.signal]
            if reset_port.direction != PortDirection.INPUT:
                raise ValueError(f"Reset signal '{self.reset.signal}' must refer to an input port")
            if reset_port.width != 1:
                raise ValueError(f"Reset signal '{self.reset.signal}' must be 1 bit wide")
            if reset_port.role != PortRole.RESET:
                raise ValueError(f"Reset signal '{self.reset.signal}' must use role 'reset'")

        if self.semantics is not None or self.semantic_constraints is not None:
            from rtl_assistant.semantics.validator import validate_hardware_semantics

            validate_hardware_semantics(self)

        return self
