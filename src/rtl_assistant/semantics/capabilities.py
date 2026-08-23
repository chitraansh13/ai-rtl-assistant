from __future__ import annotations

from dataclasses import dataclass, field
import re

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.semantics import (
    BinaryExpr,
    BitSelectExpr,
    CombinationalSemantics,
    ExtendExpr,
    LiteralExpr,
    SelectExpr,
    SemanticExpr,
    SignalExpr,
    UnaryExpr,
)


@dataclass(frozen=True)
class CapabilityPathMatch:
    assignments: dict[str, int] = field(default_factory=dict)
    unresolved_path: bool = False


def normalize_semantic_capability_token(value: str) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")
    return normalized or None


def derive_combinational_semantic_capabilities(combinational: CombinationalSemantics) -> set[str]:
    capabilities: set[str] = set()
    for assignment in combinational.assignments:
        capabilities.update(_collect_expr_capabilities(assignment.expression))
    return capabilities


def derive_semantic_capabilities(hardware_spec: HardwareSpec) -> set[str]:
    semantics = hardware_spec.semantics
    if semantics is None or semantics.combinational is None:
        return set()
    return derive_combinational_semantic_capabilities(semantics.combinational)


def _collect_expr_capabilities(expr: SemanticExpr) -> set[str]:
    if isinstance(expr, BinaryExpr):
        return {expr.op.value} | _collect_expr_capabilities(expr.left) | _collect_expr_capabilities(expr.right)
    if isinstance(expr, UnaryExpr):
        return {expr.op.value} | _collect_expr_capabilities(expr.operand)
    if isinstance(expr, SelectExpr):
        return (
            {"SELECT"}
            | _collect_expr_capabilities(expr.condition)
            | _collect_expr_capabilities(expr.when_true)
            | _collect_expr_capabilities(expr.when_false)
        )
    if isinstance(expr, BitSelectExpr):
        return {"BIT_SELECT"} | _collect_expr_capabilities(expr.signal)
    if isinstance(expr, ExtendExpr):
        return {"WIDTH_EXTEND"} | _collect_expr_capabilities(expr.operand)
    return set()


def find_capability_path_matches(hardware_spec: HardwareSpec, capability: str) -> list[CapabilityPathMatch]:
    semantics = hardware_spec.semantics
    if semantics is None or semantics.combinational is None:
        return []

    matches: list[CapabilityPathMatch] = []
    for assignment in semantics.combinational.assignments:
        matches.extend(_find_expr_capability_matches(assignment.expression, capability, {}))
    return matches


def _find_expr_capability_matches(
    expr: SemanticExpr,
    capability: str,
    assignments: dict[str, int],
) -> list[CapabilityPathMatch]:
    matches: list[CapabilityPathMatch] = []
    if capability in _collect_expr_capabilities(expr):
        matches.append(CapabilityPathMatch(assignments=dict(assignments), unresolved_path=False))

    if isinstance(expr, BinaryExpr):
        matches.extend(_find_expr_capability_matches(expr.left, capability, assignments))
        matches.extend(_find_expr_capability_matches(expr.right, capability, assignments))
        return matches

    if isinstance(expr, UnaryExpr):
        matches.extend(_find_expr_capability_matches(expr.operand, capability, assignments))
        return matches

    if isinstance(expr, BitSelectExpr):
        matches.extend(_find_expr_capability_matches(expr.signal, capability, assignments))
        return matches

    if isinstance(expr, ExtendExpr):
        matches.extend(_find_expr_capability_matches(expr.operand, capability, assignments))
        return matches

    if isinstance(expr, SelectExpr):
        control = _extract_simple_select_assignment(expr.condition)
        if control is None:
            unresolved_matches = _find_expr_capability_matches(expr.when_true, capability, assignments)
            unresolved_matches.extend(_find_expr_capability_matches(expr.when_false, capability, assignments))
            return [
                CapabilityPathMatch(assignments=match.assignments, unresolved_path=True)
                for match in unresolved_matches
            ]

        control_signal, control_value = control
        true_assignments = dict(assignments)
        true_assignments[control_signal] = control_value
        false_assignments = dict(assignments)
        false_assignments[control_signal] = 0 if control_value else 1
        matches.extend(_find_expr_capability_matches(expr.when_true, capability, true_assignments))
        matches.extend(_find_expr_capability_matches(expr.when_false, capability, false_assignments))
        return matches

    return matches


def _extract_simple_select_assignment(expr: SemanticExpr) -> tuple[str, int] | None:
    if isinstance(expr, SignalExpr):
        return expr.name, 1
    if isinstance(expr, BinaryExpr) and expr.op.value == "EQ":
        if isinstance(expr.left, SignalExpr) and isinstance(expr.right, LiteralExpr):
            return expr.left.name, expr.right.value
        if isinstance(expr.right, SignalExpr) and isinstance(expr.left, LiteralExpr):
            return expr.right.name, expr.left.value
    return None
