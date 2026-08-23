from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from rtl_assistant.models.hardware_intent import (
    CombinationalHardwareIntent,
    HardwareIntent,
    IntentAssignment,
    IntentBinaryExpr,
    IntentBinaryOp,
    IntentBitSelectExpr,
    IntentCaseSelectExpr,
    IntentConditionalExpr,
    IntentExpr,
    IntentExtendExpr,
    IntentExtendMode,
    IntentLiteralExpr,
    IntentPrioritySelectExpr,
    IntentSignalExpr,
    IntentUnaryExpr,
    IntentUnaryOp,
    PriorityDirection,
)
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.semantic_feature import (
    BinaryOperationFeature,
    BitSelectFeature,
    CaseSelectFeature,
    CompareFeature,
    ConditionalFeature,
    NonZeroFeature,
    PrioritySelectFeature,
    SemanticBinaryOp,
    SemanticCompareOp,
    SemanticExtendMode,
    SemanticFeature,
    SemanticFeatureDirection,
    SemanticFeatureOutputMode,
    WidthExtendFeature,
)
from rtl_assistant.models.semantics import (
    BinaryExpr,
    BinarySemanticOp,
    BitSelectExpr,
    CombinationalSemantics,
    ExtendExpr,
    ExtendMode,
    HardwareSemantics,
    LiteralExpr,
    SelectExpr,
    SemanticAssignment,
    SemanticConstraints,
    SignalExpr,
    UnaryExpr,
    UnarySemanticOp,
)
from rtl_assistant.semantics.validator import validate_hardware_semantics


class HardwareIntentCompilationError(ValueError):
    pass


@dataclass(frozen=True)
class ExprWidth:
    width: int
    signed: bool = False


INTENT_BINARY_TO_SEMANTIC: dict[IntentBinaryOp, BinarySemanticOp] = {
    IntentBinaryOp.ADD: BinarySemanticOp.ADD,
    IntentBinaryOp.SUB: BinarySemanticOp.SUB,
    IntentBinaryOp.BIT_AND: BinarySemanticOp.BIT_AND,
    IntentBinaryOp.BIT_OR: BinarySemanticOp.BIT_OR,
    IntentBinaryOp.BIT_XOR: BinarySemanticOp.BIT_XOR,
    IntentBinaryOp.EQ: BinarySemanticOp.EQ,
    IntentBinaryOp.NE: BinarySemanticOp.NE,
    IntentBinaryOp.LT: BinarySemanticOp.LT,
    IntentBinaryOp.LE: BinarySemanticOp.LE,
    IntentBinaryOp.GT: BinarySemanticOp.GT,
    IntentBinaryOp.GE: BinarySemanticOp.GE,
    IntentBinaryOp.SHIFT_LEFT: BinarySemanticOp.SHIFT_LEFT,
    IntentBinaryOp.SHIFT_RIGHT: BinarySemanticOp.SHIFT_RIGHT,
    IntentBinaryOp.LOGICAL_AND: BinarySemanticOp.LOGICAL_AND,
    IntentBinaryOp.LOGICAL_OR: BinarySemanticOp.LOGICAL_OR,
}


COMPARE_OPS = {
    IntentBinaryOp.EQ,
    IntentBinaryOp.NE,
    IntentBinaryOp.LT,
    IntentBinaryOp.LE,
    IntentBinaryOp.GT,
    IntentBinaryOp.GE,
}


BINARY_FEATURE_OPS = {
    IntentBinaryOp.ADD: SemanticBinaryOp.ADD,
    IntentBinaryOp.SUB: SemanticBinaryOp.SUB,
    IntentBinaryOp.BIT_AND: SemanticBinaryOp.BIT_AND,
    IntentBinaryOp.BIT_OR: SemanticBinaryOp.BIT_OR,
    IntentBinaryOp.BIT_XOR: SemanticBinaryOp.BIT_XOR,
    IntentBinaryOp.SHIFT_LEFT: SemanticBinaryOp.SHIFT_LEFT,
    IntentBinaryOp.SHIFT_RIGHT: SemanticBinaryOp.SHIFT_RIGHT,
}


COMPARE_FEATURE_OPS = {
    IntentBinaryOp.EQ: SemanticCompareOp.EQ,
    IntentBinaryOp.NE: SemanticCompareOp.NE,
    IntentBinaryOp.LT: SemanticCompareOp.LT,
    IntentBinaryOp.LE: SemanticCompareOp.LE,
    IntentBinaryOp.GT: SemanticCompareOp.GT,
    IntentBinaryOp.GE: SemanticCompareOp.GE,
}


def compile_hardware_intent(intent: HardwareIntent) -> HardwareSpec:
    try:
        semantics, constraints, features = compile_combinational_intent(intent)
        hardware_spec = HardwareSpec(
            module_name=intent.module_name,
            design_type=intent.design_type,
            description=intent.description,
            parameters=intent.parameters,
            ports=intent.ports,
            clock=intent.clock,
            reset=intent.reset,
            behavior=intent.behavior,
            semantics=semantics,
            semantic_constraints=constraints,
            semantic_features=features,
        )
        validate_hardware_semantics(hardware_spec)
        return hardware_spec
    except ValidationError as exc:
        raise HardwareIntentCompilationError(f"INTENT_LOWERING_FAILED: {exc}") from exc
    except HardwareIntentCompilationError:
        raise


def compile_combinational_intent(
    intent: HardwareIntent,
) -> tuple[HardwareSemantics, SemanticConstraints | None, list[SemanticFeature]]:
    if intent.combinational_intent is None:
        raise HardwareIntentCompilationError("INTENT_LOWERING_FAILED: missing combinational_intent")

    signal_map = {port.name: port for port in intent.ports}
    assignments: list[SemanticAssignment] = []
    features: list[SemanticFeature] = []

    for assignment in intent.combinational_intent.assignments:
        target_signal = signal_map.get(assignment.target)
        if target_signal is None:
            raise HardwareIntentCompilationError(
                f"INTENT_TARGET_INVALID: assignment target '{assignment.target}' is not a declared port"
            )
        lowered = lower_intent_expr(assignment.expression, signal_map)
        assignment_width = infer_intent_expr_width(assignment.expression, signal_map).width
        if assignment_width != target_signal.width:
            raise HardwareIntentCompilationError(
                f"INTENT_WIDTH_MISMATCH: target '{assignment.target}' width {target_signal.width} "
                f"does not match expression width {assignment_width}"
            )
        assignments.append(SemanticAssignment(target=assignment.target, expression=lowered))
        features.extend(extract_semantic_features_from_expr(assignment.expression, assignment.target))

    semantics = HardwareSemantics(combinational=CombinationalSemantics(assignments=assignments))
    constraints = build_constraints_for_intent(intent.combinational_intent, signal_map)
    return semantics, constraints, dedupe_semantic_features(features)


def build_constraints_for_intent(
    intent: CombinationalHardwareIntent,
    signal_map: dict[str, object],
) -> SemanticConstraints | None:
    constraints = []
    for assignment in intent.assignments:
        if isinstance(assignment.expression, IntentConditionalExpr):
            constraints.append(
                {
                    "target": assignment.target,
                    "condition": lower_intent_expr(assignment.expression.condition, signal_map),
                    "expected_expression": lower_intent_expr(assignment.expression.when_true, signal_map),
                }
            )
    if not constraints:
        return None
    return SemanticConstraints.model_validate({"conditionals": constraints})


def lower_intent_expr(expr: IntentExpr, signal_map: dict[str, object]) -> object:
    if isinstance(expr, IntentLiteralExpr):
        return LiteralExpr(value=expr.value, width=expr.width, signed=expr.signed)
    if isinstance(expr, IntentSignalExpr):
        if signal_map and expr.name not in signal_map:
            raise HardwareIntentCompilationError(f"INTENT_SIGNAL_NOT_FOUND: unknown signal '{expr.name}'")
        return SignalExpr(name=expr.name)
    if isinstance(expr, IntentUnaryExpr):
        if expr.op == IntentUnaryOp.NONZERO:
            operand_width = infer_intent_expr_width(expr.operand, signal_map).width
            return BinaryExpr(
                op=BinarySemanticOp.NE,
                left=lower_intent_expr(expr.operand, signal_map),
                right=LiteralExpr(value=0, width=operand_width),
            )
        unary_map = {
            IntentUnaryOp.BIT_NOT: UnarySemanticOp.BIT_NOT,
            IntentUnaryOp.LOGICAL_NOT: UnarySemanticOp.LOGICAL_NOT,
        }
        return UnaryExpr(op=unary_map[expr.op], operand=lower_intent_expr(expr.operand, signal_map))
    if isinstance(expr, IntentBinaryExpr):
        return BinaryExpr(
            op=INTENT_BINARY_TO_SEMANTIC[expr.op],
            left=lower_intent_expr(expr.left, signal_map),
            right=lower_intent_expr(expr.right, signal_map),
        )
    if isinstance(expr, IntentConditionalExpr):
        return SelectExpr(
            condition=lower_intent_expr(expr.condition, signal_map),
            when_true=lower_intent_expr(expr.when_true, signal_map),
            when_false=lower_intent_expr(expr.when_false, signal_map),
        )
    if isinstance(expr, IntentPrioritySelectExpr):
        return lower_priority_select(expr, signal_map)
    if isinstance(expr, IntentBitSelectExpr):
        signal_width = infer_intent_expr_width(expr.signal, signal_map).width
        if expr.index >= signal_width:
            raise HardwareIntentCompilationError(
                f"INTENT_WIDTH_MISMATCH: bit_select index {expr.index} exceeds width {signal_width}"
            )
        return BitSelectExpr(signal=lower_intent_expr(expr.signal, signal_map), index=expr.index)
    if isinstance(expr, IntentExtendExpr):
        operand_width = infer_intent_expr_width(expr.operand, signal_map).width
        if expr.target_width < operand_width:
            raise HardwareIntentCompilationError(
                f"INTENT_WIDTH_MISMATCH: extend target width {expr.target_width} is smaller than operand width {operand_width}"
            )
        return ExtendExpr(
            operand=lower_intent_expr(expr.operand, signal_map),
            target_width=expr.target_width,
            mode=ExtendMode(expr.mode.value),
        )
    if isinstance(expr, IntentCaseSelectExpr):
        return lower_case_select(expr, signal_map)
    raise HardwareIntentCompilationError(f"UNSUPPORTED_HARDWARE_INTENT: unsupported expression {type(expr).__name__}")


def lower_priority_select(expr: IntentPrioritySelectExpr, signal_map: dict[str, object]) -> SelectExpr | LiteralExpr:
    signal = signal_map.get(expr.source_signal)
    if signal is None:
        raise HardwareIntentCompilationError(
            f"INTENT_SIGNAL_NOT_FOUND: priority_select source '{expr.source_signal}' is not a declared signal"
        )
    source_width = getattr(signal, "width")
    if source_width <= 0:
        raise HardwareIntentCompilationError("INTENT_WIDTH_MISMATCH: priority_select source width must be positive")
    result_width = max(1, (source_width - 1).bit_length())
    current_expr: SelectExpr | LiteralExpr = LiteralExpr(value=expr.default_value, width=result_width)
    indices = range(source_width - 1, -1, -1)
    if expr.direction == PriorityDirection.HIGHEST_INDEX_FIRST:
        indices = range(source_width)
    for index in indices:
        current_expr = SelectExpr(
            condition=BitSelectExpr(signal=SignalExpr(name=expr.source_signal), index=index),
            when_true=LiteralExpr(value=index, width=result_width),
            when_false=current_expr,
        )
    return current_expr


def lower_case_select(expr: IntentCaseSelectExpr, signal_map: dict[str, object]) -> SelectExpr:
    selector_width = infer_intent_expr_width(expr.selector, signal_map).width
    if selector_width <= 0:
        raise HardwareIntentCompilationError("INTENT_WIDTH_MISMATCH: case_select selector width must be positive")
    branch_width = infer_intent_expr_width(expr.default_expression, signal_map).width
    lowered_default = lower_intent_expr(expr.default_expression, signal_map)
    lowered_selector = lower_intent_expr(expr.selector, signal_map)
    current_expr = lowered_default
    for case in reversed(expr.cases):
        if case.value >= (1 << selector_width):
            raise HardwareIntentCompilationError(
                f"INTENT_WIDTH_MISMATCH: case_select value {case.value} does not fit in selector width {selector_width}"
            )
        case_width = infer_intent_expr_width(case.expression, signal_map).width
        if case_width != branch_width:
            raise HardwareIntentCompilationError(
                "INTENT_WIDTH_MISMATCH: case_select branch widths must match the default branch width"
            )
        current_expr = SelectExpr(
            condition=BinaryExpr(
                op=BinarySemanticOp.EQ,
                left=lowered_selector,
                right=LiteralExpr(value=case.value, width=selector_width),
            ),
            when_true=lower_intent_expr(case.expression, signal_map),
            when_false=current_expr,
        )
    return current_expr


def infer_intent_expr_width(expr: IntentExpr, signal_map: dict[str, object]) -> ExprWidth:
    if isinstance(expr, IntentLiteralExpr):
        return ExprWidth(width=expr.width, signed=expr.signed)
    if isinstance(expr, IntentSignalExpr):
        signal = signal_map.get(expr.name)
        if signal is None:
            raise HardwareIntentCompilationError(f"INTENT_SIGNAL_NOT_FOUND: unknown signal '{expr.name}'")
        return ExprWidth(width=getattr(signal, "width"), signed=getattr(signal, "signed", False))
    if isinstance(expr, IntentUnaryExpr):
        operand = infer_intent_expr_width(expr.operand, signal_map)
        if expr.op == IntentUnaryOp.NONZERO or expr.op == IntentUnaryOp.LOGICAL_NOT:
            return ExprWidth(width=1, signed=False)
        return operand
    if isinstance(expr, IntentBinaryExpr):
        left = infer_intent_expr_width(expr.left, signal_map)
        right = infer_intent_expr_width(expr.right, signal_map)
        if expr.op in COMPARE_OPS or expr.op in {IntentBinaryOp.LOGICAL_AND, IntentBinaryOp.LOGICAL_OR}:
            return ExprWidth(width=1, signed=False)
        if expr.op in {IntentBinaryOp.SHIFT_LEFT, IntentBinaryOp.SHIFT_RIGHT}:
            return left
        return ExprWidth(width=max(left.width, right.width), signed=left.signed or right.signed)
    if isinstance(expr, IntentConditionalExpr):
        true_width = infer_intent_expr_width(expr.when_true, signal_map)
        false_width = infer_intent_expr_width(expr.when_false, signal_map)
        if true_width.width != false_width.width:
            raise HardwareIntentCompilationError(
                "INTENT_WIDTH_MISMATCH: conditional branches must have the same result width"
            )
        return true_width
    if isinstance(expr, IntentPrioritySelectExpr):
        signal = signal_map.get(expr.source_signal)
        if signal is None:
            raise HardwareIntentCompilationError(
                f"INTENT_SIGNAL_NOT_FOUND: priority_select source '{expr.source_signal}' is not a declared signal"
            )
        return ExprWidth(width=max(1, (getattr(signal, "width") - 1).bit_length()), signed=False)
    if isinstance(expr, IntentBitSelectExpr):
        signal_width = infer_intent_expr_width(expr.signal, signal_map).width
        if expr.index >= signal_width:
            raise HardwareIntentCompilationError(
                f"INTENT_WIDTH_MISMATCH: bit_select index {expr.index} exceeds width {signal_width}"
            )
        return ExprWidth(width=1, signed=False)
    if isinstance(expr, IntentExtendExpr):
        operand = infer_intent_expr_width(expr.operand, signal_map)
        if expr.target_width < operand.width:
            raise HardwareIntentCompilationError(
                f"INTENT_WIDTH_MISMATCH: extend target width {expr.target_width} is smaller than operand width {operand.width}"
            )
        return ExprWidth(width=expr.target_width, signed=expr.mode == IntentExtendMode.SIGN_EXTEND)
    if isinstance(expr, IntentCaseSelectExpr):
        default_width = infer_intent_expr_width(expr.default_expression, signal_map)
        selector_width = infer_intent_expr_width(expr.selector, signal_map).width
        seen: set[int] = set()
        for case in expr.cases:
            if case.value in seen:
                raise HardwareIntentCompilationError(
                    f"INTENT_WIDTH_MISMATCH: duplicate case_select selector value {case.value}"
                )
            seen.add(case.value)
            if case.value >= (1 << selector_width):
                raise HardwareIntentCompilationError(
                    f"INTENT_WIDTH_MISMATCH: case_select value {case.value} does not fit in selector width {selector_width}"
                )
            case_width = infer_intent_expr_width(case.expression, signal_map)
            if case_width.width != default_width.width:
                raise HardwareIntentCompilationError(
                    "INTENT_WIDTH_MISMATCH: case_select branch widths must match the default branch width"
                )
        return default_width
    raise HardwareIntentCompilationError(f"UNSUPPORTED_HARDWARE_INTENT: unsupported expression {type(expr).__name__}")


def extract_semantic_features_from_expr(expr: IntentExpr, target_signal: str) -> list[SemanticFeature]:
    features: list[SemanticFeature] = []
    if isinstance(expr, IntentPrioritySelectExpr):
        features.append(
            PrioritySelectFeature(
                source_signal=expr.source_signal,
                target_signal=target_signal,
                direction=SemanticFeatureDirection(expr.direction.value),
                output_mode=SemanticFeatureOutputMode(expr.output_mode.value),
                default_value=expr.default_value,
            )
        )
        return features
    if isinstance(expr, IntentCaseSelectExpr):
        selector_signal = expr.selector.name if isinstance(expr.selector, IntentSignalExpr) else None
        features.append(
            CaseSelectFeature(
                selector_signal=selector_signal,
                target_signal=target_signal,
                case_values=[case.value for case in expr.cases],
            )
        )
        for case in expr.cases:
            features.extend(extract_semantic_features_from_expr(case.expression, target_signal))
        features.extend(extract_semantic_features_from_expr(expr.default_expression, target_signal))
        return features
    if isinstance(expr, IntentConditionalExpr):
        if isinstance(expr.condition, IntentSignalExpr):
            features.append(ConditionalFeature(condition_signal=expr.condition.name, target_signal=target_signal))
        features.extend(extract_semantic_features_from_expr(expr.when_true, target_signal))
        features.extend(extract_semantic_features_from_expr(expr.when_false, target_signal))
        return features
    if isinstance(expr, IntentUnaryExpr):
        if expr.op == IntentUnaryOp.NONZERO and isinstance(expr.operand, IntentSignalExpr):
            features.append(NonZeroFeature(source_signal=expr.operand.name, target_signal=target_signal))
        features.extend(extract_semantic_features_from_expr(expr.operand, target_signal))
        return features
    if isinstance(expr, IntentBinaryExpr):
        if (
            expr.op in COMPARE_FEATURE_OPS
            and isinstance(expr.left, IntentSignalExpr)
            and isinstance(expr.right, IntentSignalExpr)
        ):
            features.append(
                CompareFeature(
                    left_signal=expr.left.name,
                    right_signal=expr.right.name,
                    target_signal=target_signal,
                    operation=COMPARE_FEATURE_OPS[expr.op],
                )
            )
        elif (
            expr.op in BINARY_FEATURE_OPS
            and isinstance(expr.left, IntentSignalExpr)
            and isinstance(expr.right, IntentSignalExpr)
        ):
            features.append(
                BinaryOperationFeature(
                    left_signal=expr.left.name,
                    right_signal=expr.right.name,
                    target_signal=target_signal,
                    operation=BINARY_FEATURE_OPS[expr.op],
                )
            )
        features.extend(extract_semantic_features_from_expr(expr.left, target_signal))
        features.extend(extract_semantic_features_from_expr(expr.right, target_signal))
        return features
    if isinstance(expr, IntentBitSelectExpr):
        source_signal = expr.signal.name if isinstance(expr.signal, IntentSignalExpr) else None
        features.append(BitSelectFeature(source_signal=source_signal, target_signal=target_signal, index=expr.index))
        features.extend(extract_semantic_features_from_expr(expr.signal, target_signal))
        return features
    if isinstance(expr, IntentExtendExpr):
        source_signal = expr.operand.name if isinstance(expr.operand, IntentSignalExpr) else None
        features.append(
            WidthExtendFeature(
                source_signal=source_signal,
                target_signal=target_signal,
                mode=SemanticExtendMode(expr.mode.value),
                target_width=expr.target_width,
            )
        )
        features.extend(extract_semantic_features_from_expr(expr.operand, target_signal))
        return features
    return features


def dedupe_semantic_features(features: list[SemanticFeature]) -> list[SemanticFeature]:
    deduped: list[SemanticFeature] = []
    seen: set[tuple] = set()
    for feature in features:
        key = (feature.kind, feature.model_dump_json())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(feature)
    return deduped
