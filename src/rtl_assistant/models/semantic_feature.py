from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class SemanticFeatureDirection(str, Enum):
    LOWEST_INDEX_FIRST = "LOWEST_INDEX_FIRST"
    HIGHEST_INDEX_FIRST = "HIGHEST_INDEX_FIRST"


class SemanticFeatureOutputMode(str, Enum):
    INDEX = "INDEX"


class SemanticCompareOp(str, Enum):
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"


class SemanticBinaryOp(str, Enum):
    ADD = "ADD"
    SUB = "SUB"
    BIT_AND = "BIT_AND"
    BIT_OR = "BIT_OR"
    BIT_XOR = "BIT_XOR"
    SHIFT_LEFT = "SHIFT_LEFT"
    SHIFT_RIGHT = "SHIFT_RIGHT"


class SemanticExtendMode(str, Enum):
    ZERO_EXTEND = "ZERO_EXTEND"
    SIGN_EXTEND = "SIGN_EXTEND"


class PrioritySelectFeature(BaseModel):
    kind: Literal["PRIORITY_SELECT"] = "PRIORITY_SELECT"
    source_signal: str
    target_signal: str
    direction: SemanticFeatureDirection
    output_mode: SemanticFeatureOutputMode
    default_value: int = 0


class NonZeroFeature(BaseModel):
    kind: Literal["NONZERO"] = "NONZERO"
    source_signal: str
    target_signal: str


class ConditionalFeature(BaseModel):
    kind: Literal["CONDITIONAL"] = "CONDITIONAL"
    condition_signal: str
    target_signal: str


class CompareFeature(BaseModel):
    kind: Literal["COMPARE"] = "COMPARE"
    left_signal: str
    right_signal: str
    target_signal: str
    operation: SemanticCompareOp


class BinaryOperationFeature(BaseModel):
    kind: Literal["BINARY_OPERATION"] = "BINARY_OPERATION"
    left_signal: str
    right_signal: str
    target_signal: str
    operation: SemanticBinaryOp


class CaseSelectFeature(BaseModel):
    kind: Literal["CASE_SELECT"] = "CASE_SELECT"
    selector_signal: str | None = None
    target_signal: str
    case_values: list[int] = Field(default_factory=list)


class WidthExtendFeature(BaseModel):
    kind: Literal["WIDTH_EXTEND"] = "WIDTH_EXTEND"
    source_signal: str | None = None
    target_signal: str
    mode: SemanticExtendMode
    target_width: int = Field(ge=1)


class BitSelectFeature(BaseModel):
    kind: Literal["BIT_SELECT"] = "BIT_SELECT"
    source_signal: str | None = None
    target_signal: str
    index: int = Field(ge=0)


SemanticFeature = Annotated[
    Union[
        PrioritySelectFeature,
        NonZeroFeature,
        ConditionalFeature,
        CompareFeature,
        BinaryOperationFeature,
        CaseSelectFeature,
        WidthExtendFeature,
        BitSelectFeature,
    ],
    Field(discriminator="kind"),
]

