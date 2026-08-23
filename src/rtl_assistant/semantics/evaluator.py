from __future__ import annotations

from dataclasses import dataclass

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.semantics import (
    BinaryExpr,
    BinarySemanticOp,
    BitSelectExpr,
    CombinationalSemantics,
    ExtendExpr,
    ExtendMode,
    LiteralExpr,
    SelectExpr,
    SemanticExpr,
    SignalExpr,
    UnaryExpr,
    UnarySemanticOp,
)


class SemanticEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluatedValue:
    value: int
    width: int
    signed: bool = False


def evaluate_combinational_semantics(
    hardware_spec: HardwareSpec,
    semantics: CombinationalSemantics,
    inputs: dict[str, int],
) -> dict[str, int]:
    if semantics is None:
        raise SemanticEvaluationError("UNRESOLVED_SEMANTICS: combinational semantics are required for evaluation")

    ports_by_name = {signal.name: signal for signal in hardware_spec.ports}
    assignment_map = {
        assignment.target: assignment.expression for assignment in semantics.assignments
    }
    cache: dict[str, EvaluatedValue] = {}
    evaluating: set[str] = set()

    def eval_assignment(target: str) -> EvaluatedValue:
        if target in cache:
            return cache[target]
        if target in evaluating:
            raise SemanticEvaluationError(f"SEMANTIC_CYCLE: combinational assignment cycle detected at '{target}'")
        evaluating.add(target)
        result = evaluate_expr(assignment_map[target])
        evaluating.remove(target)
        cache[target] = result
        return result

    def evaluate_expr(expr: SemanticExpr) -> EvaluatedValue:
        if isinstance(expr, LiteralExpr):
            return EvaluatedValue(mask_value(expr.value, expr.width), expr.width, expr.signed)

        if isinstance(expr, SignalExpr):
            if expr.name in inputs:
                signal = ports_by_name.get(expr.name)
                if signal is None:
                    raise SemanticEvaluationError(f"INVALID_SEMANTIC_REFERENCE: unknown signal '{expr.name}'")
                return EvaluatedValue(
                    mask_value(inputs[expr.name], signal.width),
                    signal.width,
                    getattr(signal, "signed", False),
                )
            if expr.name in assignment_map:
                return eval_assignment(expr.name)
            raise SemanticEvaluationError(f"INVALID_SEMANTIC_REFERENCE: unknown signal '{expr.name}'")

        if isinstance(expr, BitSelectExpr):
            source = evaluate_expr(expr.signal)
            if expr.index >= source.width:
                raise SemanticEvaluationError(
                    f"SEMANTIC_WIDTH_MISMATCH: bit_select index {expr.index} exceeds width {source.width}"
                )
            return EvaluatedValue((source.value >> expr.index) & 1, 1, False)

        if isinstance(expr, ExtendExpr):
            operand = evaluate_expr(expr.operand)
            if expr.target_width < operand.width:
                raise SemanticEvaluationError(
                    f"SEMANTIC_WIDTH_MISMATCH: extend target width {expr.target_width} is smaller than operand width {operand.width}"
                )
            value = mask_value(operand.value, operand.width)
            if expr.mode == ExtendMode.SIGN_EXTEND and operand.width > 0:
                sign_bit = 1 << (operand.width - 1)
                if value & sign_bit:
                    extension_mask = ((1 << (expr.target_width - operand.width)) - 1) << operand.width
                    value |= extension_mask
            return EvaluatedValue(mask_value(value, expr.target_width), expr.target_width, expr.mode == ExtendMode.SIGN_EXTEND)

        if isinstance(expr, UnaryExpr):
            operand = evaluate_expr(expr.operand)
            if expr.op == UnarySemanticOp.BIT_NOT:
                return EvaluatedValue(mask_value(~operand.value, operand.width), operand.width, operand.signed)
            if expr.op == UnarySemanticOp.LOGICAL_NOT:
                return EvaluatedValue(0 if operand.value else 1, 1, False)
            raise SemanticEvaluationError(f"UNSUPPORTED_SEMANTIC_EXPRESSION: unsupported unary op {expr.op}")

        if isinstance(expr, BinaryExpr):
            left = evaluate_expr(expr.left)
            right = evaluate_expr(expr.right)
            return evaluate_binary_expr(expr.op, left, right)

        if isinstance(expr, SelectExpr):
            condition = evaluate_expr(expr.condition)
            if condition.width != 1:
                raise SemanticEvaluationError("SEMANTIC_WIDTH_MISMATCH: select condition must be 1 bit wide")
            return evaluate_expr(expr.when_true if condition.value else expr.when_false)

        raise SemanticEvaluationError(f"UNSUPPORTED_SEMANTIC_EXPRESSION: unsupported expression {type(expr).__name__}")

    return {target: eval_assignment(target).value for target in assignment_map}


def evaluate_binary_expr(op: BinarySemanticOp, left: EvaluatedValue, right: EvaluatedValue) -> EvaluatedValue:
    result_width = max(left.width, right.width)
    left_value = mask_value(left.value, left.width)
    right_value = mask_value(right.value, right.width)

    if op == BinarySemanticOp.ADD:
        return EvaluatedValue(mask_value(left_value + right_value, result_width), result_width, left.signed or right.signed)
    if op == BinarySemanticOp.SUB:
        return EvaluatedValue(mask_value(left_value - right_value, result_width), result_width, left.signed or right.signed)
    if op == BinarySemanticOp.BIT_AND:
        return EvaluatedValue(mask_value(left_value & right_value, result_width), result_width, left.signed or right.signed)
    if op == BinarySemanticOp.BIT_OR:
        return EvaluatedValue(mask_value(left_value | right_value, result_width), result_width, left.signed or right.signed)
    if op == BinarySemanticOp.BIT_XOR:
        return EvaluatedValue(mask_value(left_value ^ right_value, result_width), result_width, left.signed or right.signed)
    if op == BinarySemanticOp.EQ:
        return EvaluatedValue(1 if left_value == right_value else 0, 1, False)
    if op == BinarySemanticOp.NE:
        return EvaluatedValue(1 if left_value != right_value else 0, 1, False)
    if op == BinarySemanticOp.LT:
        return EvaluatedValue(1 if compare_value(left) < compare_value(right) else 0, 1, False)
    if op == BinarySemanticOp.LE:
        return EvaluatedValue(1 if compare_value(left) <= compare_value(right) else 0, 1, False)
    if op == BinarySemanticOp.GT:
        return EvaluatedValue(1 if compare_value(left) > compare_value(right) else 0, 1, False)
    if op == BinarySemanticOp.GE:
        return EvaluatedValue(1 if compare_value(left) >= compare_value(right) else 0, 1, False)
    if op == BinarySemanticOp.SHIFT_LEFT:
        return EvaluatedValue(mask_value(left_value << right_value, left.width), left.width, left.signed)
    if op == BinarySemanticOp.SHIFT_RIGHT:
        if left.signed:
            signed_left = compare_value(left)
            return EvaluatedValue(mask_value(signed_left >> right_value, left.width), left.width, True)
        return EvaluatedValue(mask_value(left_value >> right_value, left.width), left.width, False)
    if op == BinarySemanticOp.LOGICAL_AND:
        return EvaluatedValue(1 if left_value and right_value else 0, 1, False)
    if op == BinarySemanticOp.LOGICAL_OR:
        return EvaluatedValue(1 if left_value or right_value else 0, 1, False)
    raise SemanticEvaluationError(f"UNSUPPORTED_SEMANTIC_EXPRESSION: unsupported binary op {op}")


def compare_value(value: EvaluatedValue) -> int:
    masked = mask_value(value.value, value.width)
    if not value.signed or value.width <= 0:
        return masked
    sign_bit = 1 << (value.width - 1)
    return masked - (1 << value.width) if masked & sign_bit else masked


def mask_value(value: int, width: int) -> int:
    return value & ((1 << width) - 1)
