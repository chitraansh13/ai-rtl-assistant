from __future__ import annotations

from dataclasses import dataclass

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.semantics import (
    BinaryExpr,
    BinarySemanticOp,
    BitSelectExpr,
    ExtendExpr,
    ExtendMode,
    LiteralExpr,
    SelectExpr,
    SemanticAssignment,
    SemanticExpr,
    SignalExpr,
    UnaryExpr,
)


class SemanticValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ExprType:
    width: int
    signed: bool = False


def validate_hardware_semantics(hardware_spec: HardwareSpec) -> None:
    semantics = hardware_spec.semantics
    if semantics is None or semantics.combinational is None:
        return

    signal_map = {signal.name: signal for signal in hardware_spec.ports}
    assignments = {assignment.target: assignment.expression for assignment in semantics.combinational.assignments}

    for assignment in semantics.combinational.assignments:
        target_signal = signal_map.get(assignment.target)
        if target_signal is None or target_signal.direction != "output":
            raise SemanticValidationError(
                f"INVALID_SEMANTIC_TARGET: combinational assignment target '{assignment.target}' must be a declared output"
            )
        expr_type = _validate_expr(assignment.expression, signal_map, assignments, assignment.target)
        if expr_type.width != target_signal.width:
            raise SemanticValidationError(
                f"SEMANTIC_WIDTH_MISMATCH: target '{assignment.target}' width {target_signal.width} does not match expression width {expr_type.width}"
            )

    _validate_assignment_dependency_cycles(assignments)


def _validate_expr(
    expr: SemanticExpr,
    signal_map: dict[str, object],
    assignments: dict[str, SemanticExpr],
    current_target: str | None,
) -> ExprType:
    if isinstance(expr, LiteralExpr):
        return ExprType(width=expr.width, signed=expr.signed)

    if isinstance(expr, SignalExpr):
        signal = signal_map.get(expr.name)
        if signal is not None:
            return ExprType(width=getattr(signal, "width"), signed=getattr(signal, "signed", False))
        assignment_expr = assignments.get(expr.name)
        if assignment_expr is None:
            raise SemanticValidationError(f"INVALID_SEMANTIC_REFERENCE: unknown signal '{expr.name}'")
        if expr.name == current_target:
            raise SemanticValidationError(
                f"SEMANTIC_CYCLE: output '{expr.name}' references itself combinationally"
            )
        return _validate_expr(assignment_expr, signal_map, assignments, expr.name)

    if isinstance(expr, BitSelectExpr):
        source_type = _validate_expr(expr.signal, signal_map, assignments, current_target)
        if expr.index >= source_type.width:
            raise SemanticValidationError(
                f"SEMANTIC_WIDTH_MISMATCH: bit_select index {expr.index} exceeds width {source_type.width}"
            )
        return ExprType(width=1, signed=False)

    if isinstance(expr, ExtendExpr):
        operand_type = _validate_expr(expr.operand, signal_map, assignments, current_target)
        if expr.target_width < operand_type.width:
            raise SemanticValidationError(
                f"SEMANTIC_WIDTH_MISMATCH: extend target width {expr.target_width} is smaller than operand width {operand_type.width}"
            )
        return ExprType(width=expr.target_width, signed=expr.mode == ExtendMode.SIGN_EXTEND)

    if isinstance(expr, UnaryExpr):
        operand_type = _validate_expr(expr.operand, signal_map, assignments, current_target)
        if expr.op.name == "LOGICAL_NOT":
            return ExprType(width=1, signed=False)
        return operand_type

    if isinstance(expr, BinaryExpr):
        left_type = _validate_expr(expr.left, signal_map, assignments, current_target)
        right_type = _validate_expr(expr.right, signal_map, assignments, current_target)
        if expr.op in {
            BinarySemanticOp.EQ,
            BinarySemanticOp.NE,
            BinarySemanticOp.LT,
            BinarySemanticOp.LE,
            BinarySemanticOp.GT,
            BinarySemanticOp.GE,
            BinarySemanticOp.LOGICAL_AND,
            BinarySemanticOp.LOGICAL_OR,
        }:
            return ExprType(width=1, signed=False)
        if expr.op in {BinarySemanticOp.SHIFT_LEFT, BinarySemanticOp.SHIFT_RIGHT}:
            return left_type
        return ExprType(width=max(left_type.width, right_type.width), signed=left_type.signed or right_type.signed)

    if isinstance(expr, SelectExpr):
        condition_type = _validate_expr(expr.condition, signal_map, assignments, current_target)
        if condition_type.width != 1:
            raise SemanticValidationError("SEMANTIC_WIDTH_MISMATCH: select condition must be 1 bit wide")
        true_type = _validate_expr(expr.when_true, signal_map, assignments, current_target)
        false_type = _validate_expr(expr.when_false, signal_map, assignments, current_target)
        if true_type.width != false_type.width:
            raise SemanticValidationError(
                "SEMANTIC_WIDTH_MISMATCH: select branches must have the same width"
            )
        return true_type

    raise SemanticValidationError(f"UNSUPPORTED_SEMANTIC_EXPRESSION: unsupported expression {type(expr).__name__}")


def _validate_assignment_dependency_cycles(assignments: dict[str, SemanticExpr]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(target: str) -> None:
        if target in visited:
            return
        if target in visiting:
            raise SemanticValidationError(f"SEMANTIC_CYCLE: combinational assignment cycle detected at '{target}'")
        visiting.add(target)
        for dependency in _collect_assignment_dependencies(assignments[target], assignments):
            visit(dependency)
        visiting.remove(target)
        visited.add(target)

    for target in assignments:
        visit(target)


def _collect_assignment_dependencies(expr: SemanticExpr, assignments: dict[str, SemanticExpr]) -> set[str]:
    if isinstance(expr, SignalExpr):
        return {expr.name} if expr.name in assignments else set()
    if isinstance(expr, BitSelectExpr):
        return _collect_assignment_dependencies(expr.signal, assignments)
    if isinstance(expr, ExtendExpr):
        return _collect_assignment_dependencies(expr.operand, assignments)
    if isinstance(expr, UnaryExpr):
        return _collect_assignment_dependencies(expr.operand, assignments)
    if isinstance(expr, BinaryExpr):
        return _collect_assignment_dependencies(expr.left, assignments) | _collect_assignment_dependencies(
            expr.right, assignments
        )
    if isinstance(expr, SelectExpr):
        return (
            _collect_assignment_dependencies(expr.condition, assignments)
            | _collect_assignment_dependencies(expr.when_true, assignments)
            | _collect_assignment_dependencies(expr.when_false, assignments)
        )
    return set()

