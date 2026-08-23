from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class UnarySemanticOp(str, Enum):
    BIT_NOT = "BIT_NOT"
    LOGICAL_NOT = "LOGICAL_NOT"


class BinarySemanticOp(str, Enum):
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


class ExtendMode(str, Enum):
    ZERO_EXTEND = "ZERO_EXTEND"
    SIGN_EXTEND = "SIGN_EXTEND"


class LiteralExpr(BaseModel):
    type: Literal["literal"] = "literal"
    value: int
    width: int = Field(ge=1)
    signed: bool = False


class SignalExpr(BaseModel):
    type: Literal["signal"] = "signal"
    name: str


class BitSelectExpr(BaseModel):
    type: Literal["bit_select"] = "bit_select"
    signal: "SemanticExpr"
    index: int = Field(ge=0)


class UnaryExpr(BaseModel):
    type: Literal["unary"] = "unary"
    op: UnarySemanticOp
    operand: "SemanticExpr"


class BinaryExpr(BaseModel):
    type: Literal["binary"] = "binary"
    op: BinarySemanticOp
    left: "SemanticExpr"
    right: "SemanticExpr"


class SelectExpr(BaseModel):
    type: Literal["select"] = "select"
    condition: "SemanticExpr"
    when_true: "SemanticExpr"
    when_false: "SemanticExpr"


class ExtendExpr(BaseModel):
    type: Literal["extend"] = "extend"
    operand: "SemanticExpr"
    target_width: int = Field(ge=1)
    mode: ExtendMode


SemanticExpr = Annotated[
    Union[
        LiteralExpr,
        SignalExpr,
        BitSelectExpr,
        UnaryExpr,
        BinaryExpr,
        SelectExpr,
        ExtendExpr,
    ],
    Field(discriminator="type"),
]


class SemanticAssignment(BaseModel):
    target: str
    expression: SemanticExpr


class ConditionalBehaviorConstraint(BaseModel):
    target: str
    condition: SemanticExpr | None = None
    expected_expression: SemanticExpr
    control_signal: str | None = None
    control_value: int | None = None

    @model_validator(mode="after")
    def normalize_legacy_condition(self) -> "ConditionalBehaviorConstraint":
        if self.condition is None and self.control_signal is not None and self.control_value is not None:
            self.condition = BinaryExpr(
                op=BinarySemanticOp.EQ,
                left=SignalExpr(name=self.control_signal),
                right=LiteralExpr(value=self.control_value, width=1),
            )
        if self.condition is None:
            raise ValueError("Conditional constraint requires a structured condition")
        return self


class SemanticConstraints(BaseModel):
    conditionals: list[ConditionalBehaviorConstraint] = Field(default_factory=list)


class CombinationalSemantics(BaseModel):
    assignments: list[SemanticAssignment]

    @model_validator(mode="after")
    def validate_unique_targets(self) -> "CombinationalSemantics":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for assignment in self.assignments:
            if assignment.target in seen:
                duplicates.add(assignment.target)
            seen.add(assignment.target)
        if duplicates:
            duplicate_text = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate combinational semantic assignment targets: {duplicate_text}")
        return self


class HardwareSemantics(BaseModel):
    combinational: CombinationalSemantics | None = None

    @model_validator(mode="after")
    def require_at_least_one_section(self) -> "HardwareSemantics":
        if self.combinational is None:
            raise ValueError("Hardware semantics require at least one supported section")
        return self

