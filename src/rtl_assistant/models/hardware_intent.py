from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

from rtl_assistant.models.hardware_spec import (
    BehaviorSpec,
    ClockSpec,
    DesignType,
    ParameterSpec,
    PortSpec,
    ResetSpec,
)


class IntentUnaryOp(str, Enum):
    NONZERO = "NONZERO"
    BIT_NOT = "BIT_NOT"
    LOGICAL_NOT = "LOGICAL_NOT"


class IntentBinaryOp(str, Enum):
    ADD = "ADD"
    SUB = "SUB"
    BIT_AND = "BIT_AND"
    BIT_OR = "BIT_OR"
    BIT_XOR = "BIT_XOR"
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    SHIFT_LEFT = "SHIFT_LEFT"
    SHIFT_RIGHT = "SHIFT_RIGHT"
    LOGICAL_AND = "LOGICAL_AND"
    LOGICAL_OR = "LOGICAL_OR"


class IntentExtendMode(str, Enum):
    ZERO_EXTEND = "ZERO_EXTEND"
    SIGN_EXTEND = "SIGN_EXTEND"


class PriorityDirection(str, Enum):
    LOWEST_INDEX_FIRST = "LOWEST_INDEX_FIRST"
    HIGHEST_INDEX_FIRST = "HIGHEST_INDEX_FIRST"


class PriorityOutputMode(str, Enum):
    INDEX = "INDEX"


class IntentLiteralExpr(BaseModel):
    type: Literal["literal"] = "literal"
    value: int
    width: int = Field(ge=1)
    signed: bool = False


class IntentSignalExpr(BaseModel):
    type: Literal["signal"] = "signal"
    name: str


class IntentUnaryExpr(BaseModel):
    type: Literal["unary"] = "unary"
    op: IntentUnaryOp
    operand: "IntentExpr"


class IntentBinaryExpr(BaseModel):
    type: Literal["binary"] = "binary"
    op: IntentBinaryOp
    left: "IntentExpr"
    right: "IntentExpr"


class IntentConditionalExpr(BaseModel):
    type: Literal["conditional"] = "conditional"
    condition: "IntentExpr"
    when_true: "IntentExpr"
    when_false: "IntentExpr"


class IntentPrioritySelectExpr(BaseModel):
    type: Literal["priority_select"] = "priority_select"
    source_signal: str
    direction: PriorityDirection
    output_mode: PriorityOutputMode = PriorityOutputMode.INDEX
    default_value: int = 0


class IntentBitSelectExpr(BaseModel):
    type: Literal["bit_select"] = "bit_select"
    signal: "IntentExpr"
    index: int = Field(ge=0)


class IntentExtendExpr(BaseModel):
    type: Literal["extend"] = "extend"
    operand: "IntentExpr"
    target_width: int = Field(ge=1)
    mode: IntentExtendMode


class IntentCaseSelectCase(BaseModel):
    value: int = Field(ge=0)
    expression: "IntentExpr"


class IntentCaseSelectExpr(BaseModel):
    type: Literal["case_select"] = "case_select"
    selector: "IntentExpr"
    cases: list[IntentCaseSelectCase] = Field(min_length=1)
    default_expression: "IntentExpr"

    @model_validator(mode="after")
    def validate_unique_case_values(self) -> "IntentCaseSelectExpr":
        seen: set[int] = set()
        duplicates: set[int] = set()
        for case in self.cases:
            if case.value in seen:
                duplicates.add(case.value)
            seen.add(case.value)
        if duplicates:
            duplicate_text = ", ".join(str(value) for value in sorted(duplicates))
            raise ValueError(f"Duplicate case_select values: {duplicate_text}")
        return self


IntentExpr = Annotated[
    Union[
        IntentLiteralExpr,
        IntentSignalExpr,
        IntentUnaryExpr,
        IntentBinaryExpr,
        IntentConditionalExpr,
        IntentPrioritySelectExpr,
        IntentBitSelectExpr,
        IntentExtendExpr,
        IntentCaseSelectExpr,
    ],
    Field(discriminator="type"),
]


class IntentAssignment(BaseModel):
    target: str
    expression: IntentExpr


class CombinationalHardwareIntent(BaseModel):
    assignments: list[IntentAssignment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_targets(self) -> "CombinationalHardwareIntent":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for assignment in self.assignments:
            if assignment.target in seen:
                duplicates.add(assignment.target)
            seen.add(assignment.target)
        if duplicates:
            duplicate_text = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate combinational intent assignment targets: {duplicate_text}")
        return self


class HardwareIntent(BaseModel):
    schema_version: str = "1.0"
    module_name: str
    design_type: DesignType
    description: str | None = None
    parameters: list[ParameterSpec] = Field(default_factory=list)
    ports: list[PortSpec] = Field(default_factory=list)
    clock: ClockSpec | None = None
    reset: ResetSpec | None = None
    combinational_intent: CombinationalHardwareIntent | None = None
    behavior: BehaviorSpec = Field(default_factory=BehaviorSpec)
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_supported_design_type(self) -> "HardwareIntent":
        if self.design_type != DesignType.COMBINATIONAL:
            raise ValueError("Only combinational HardwareIntent is currently supported")
        if self.clock is not None or self.reset is not None:
            raise ValueError("Combinational HardwareIntent must not declare clock or reset signals")
        if self.combinational_intent is None:
            raise ValueError("Combinational HardwareIntent requires combinational_intent")
        return self
