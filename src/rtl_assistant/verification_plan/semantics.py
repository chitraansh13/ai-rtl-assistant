import re

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.semantics.capabilities import (
    derive_combinational_semantic_capabilities,
    normalize_semantic_capability_token,
)


BEHAVIOR_ALIASES: dict[str, tuple[str, ...]] = {
    "RESET": ("reset", "clear"),
    "PRIORITY_SELECT": ("priority_select", "priority select", "priority", "precedence"),
    "NONZERO": ("nonzero", "non_zero", "non-zero"),
    "ROUTING": ("route", "routing", "select_path"),
    "MUX": ("mux", "multiplex", "select"),
    "ADD": ("add", "addition"),
    "SUB": ("sub", "subtract", "subtraction"),
    "SHIFT_LEFT": ("shift_left", "shift-left", "shift left", "left shift", "shifts left"),
    "SHIFT_RIGHT": ("shift_right", "shift-right", "shift right", "right shift", "shifts right"),
    "INCREMENT": ("increment", "count up", "up-counter", "up counter"),
    "DECREMENT": ("decrement", "count down", "down-counter", "down counter"),
    "HOLD": ("hold", "holds", "unchanged", "previous value"),
    "COMPARE": ("compare", "comparison"),
    "ENCODE": ("encode", "encoding"),
    "DECODE": ("decode", "decoder", "one-hot", "one hot"),
    "EQ": ("eq", "equal", "equals", "equality"),
    "NE": ("ne", "not_equal", "not equal"),
    "LT": ("lt", "less_than", "less than"),
    "LE": ("le", "less_equal", "less or equal"),
    "GT": ("gt", "greater_than", "greater than"),
    "GE": ("ge", "greater_equal", "greater or equal"),
    "WRAPAROUND": ("wrap", "wraparound", "modulo"),
    "CARRY": ("carry", "carry_out", "carry-out"),
    "ZERO": ("zero", "zero_flag", "zero-flag"),
    "MAPPING": ("mapping", "map", "route"),
    "FUNCTIONAL": ("functional",),
}

SCENARIO_ALIASES: dict[str, tuple[str, ...]] = {
    "BASIC": ("basic",),
    "BOUNDARY": ("boundary", "max", "min"),
    "RESET_ASSERT": ("reset_assert", "reset", "reset behavior", "reset assertion"),
    "RESET_RELEASE": ("reset_release", "reset release"),
    "ENABLED_SINGLE_EDGE": ("enabled_single_edge", "single edge", "enabled transition", "single transition"),
    "ENABLED_MULTI_EDGE": ("enabled_multi_edge", "multi edge", "multiple edges", "repeated shift", "repeated transition"),
    "DISABLED_HOLD": ("disabled_hold", "hold", "disabled", "no update"),
    "MAPPING": ("mapping", "routing", "decode", "select path"),
    "ARITHMETIC": ("arithmetic",),
    "LOGIC": ("logic", "bitwise"),
}


def normalize_semantic_token(value: str) -> str:
    """Normalize one semantic token into uppercase snake case."""

    return re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")


def normalize_behavior_token(value: str) -> str | None:
    """Map behavior wording into one canonical semantic token when recognized."""

    semantic_capability = normalize_semantic_capability_token(value)
    if semantic_capability is not None:
        return semantic_capability

    normalized = normalize_semantic_token(value)
    if normalized in BEHAVIOR_ALIASES:
        return normalized

    for canonical, aliases in BEHAVIOR_ALIASES.items():
        if normalized == canonical:
            return canonical
        for alias in aliases:
            alias_normalized = normalize_semantic_token(alias)
            if normalized == alias_normalized:
                return canonical
    return None


def normalize_scenario_token(value: str) -> str | None:
    """Map scenario wording into one canonical semantic token when recognized."""

    normalized = normalize_semantic_token(value)
    if normalized in SCENARIO_ALIASES:
        return normalized

    for canonical, aliases in SCENARIO_ALIASES.items():
        if normalized == canonical:
            return canonical
        for alias in aliases:
            if normalized == normalize_semantic_token(alias):
                return canonical
    return None


def derive_supported_behaviors(hardware_spec: HardwareSpec) -> set[str]:
    """Derive canonical behavior tokens supported by the HardwareSpec."""

    supported: set[str] = set()
    behavior_text = " ".join(
        [
            hardware_spec.description or "",
            hardware_spec.behavior.description,
            *hardware_spec.behavior.operations,
            *hardware_spec.behavior.rules,
            *hardware_spec.tags,
        ]
    )

    for operation in hardware_spec.behavior.operations:
        normalized = normalize_behavior_token(operation)
        if normalized is not None:
            supported.add(normalized)

    if hardware_spec.semantics is not None and hardware_spec.semantics.combinational is not None:
        semantic_capabilities = derive_combinational_semantic_capabilities(hardware_spec.semantics.combinational)
        supported.update(semantic_capabilities)
        supported.add("FUNCTIONAL")
        supported.add("MAPPING")
        if "SELECT" in semantic_capabilities:
            supported.update({"SELECT", "MUX", "ROUTING"})
        if any(token in semantic_capabilities for token in {"EQ", "NE", "LT", "LE", "GT", "GE"}):
            supported.add("COMPARE")

    for feature in hardware_spec.semantic_features:
        supported.add(feature.kind)
        if feature.kind == "COMPARE":
            supported.add("COMPARE")

    searchable = normalize_semantic_token(behavior_text)
    for canonical, aliases in BEHAVIOR_ALIASES.items():
        alias_tokens = [normalize_semantic_token(canonical), *(normalize_semantic_token(alias) for alias in aliases)]
        if any(alias_token and re.search(rf"(?<![A-Z0-9]){re.escape(alias_token)}(?![A-Z0-9])", searchable) for alias_token in alias_tokens):
            supported.add(canonical)

    return supported
