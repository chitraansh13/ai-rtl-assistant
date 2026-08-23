from enum import Enum


class TestCategory(str, Enum):
    """High-level verification test categories shared across intent and compiled plans."""

    BASIC = "BASIC"
    FUNCTIONAL = "FUNCTIONAL"
    RESET = "RESET"
    CONTROL = "CONTROL"
    EDGE_CASE = "EDGE_CASE"
    BOUNDARY = "BOUNDARY"
    STATE_TRANSITION = "STATE_TRANSITION"
    ARITHMETIC = "ARITHMETIC"
    INVALID_OR_GUARDED = "INVALID_OR_GUARDED"
    OTHER = "OTHER"
