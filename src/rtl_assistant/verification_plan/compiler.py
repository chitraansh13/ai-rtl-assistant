from dataclasses import dataclass

from rtl_assistant.models.compiled_verification_plan import (
    CompiledVerificationCase,
    CompiledVerificationPlan,
)
from rtl_assistant.models.hardware_spec import HardwareSpec, PortDirection, PortRole, ResetPolarity, ResetType
from rtl_assistant.models.semantic_feature import (
    NonZeroFeature,
    PrioritySelectFeature,
)
from rtl_assistant.models.verification_intent import VerificationIntentCase, VerificationIntentPlan
from rtl_assistant.reference.handlers.alu import (
    compute_unsigned_alu_outputs,
    extract_alu_opcode_mapping,
    normalize_opcode_token,
    parse_numeric_literal,
)
from rtl_assistant.reference.handlers.shift import (
    compute_shift_next_state,
    infer_serial_input_signal,
    infer_shift_direction,
    infer_shift_state_output,
)
from rtl_assistant.semantics.capabilities import find_capability_path_matches
from rtl_assistant.semantics.evaluator import (
    SemanticEvaluationError,
    evaluate_combinational_semantics,
)
from rtl_assistant.testbench.ir import ExpectedCheck, InputAssignment, TestbenchAction, TestbenchActionType
from rtl_assistant.verification_plan.semantics import (
    derive_supported_behaviors,
    normalize_behavior_token,
    normalize_scenario_token,
)


class VerificationCompilationError(Exception):
    """Structured deterministic verification-compilation failure."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(f"{error_type}: {message}")
        self.error_type = error_type
        self.message = message


@dataclass(slots=True)
class KnownState:
    """Current deterministically known observable state for one sequential output."""

    signal: str
    value: int
    provenance: str


def compile_verification_intent_plan(
    hardware_spec: HardwareSpec,
    intent_plan: VerificationIntentPlan,
) -> CompiledVerificationPlan:
    """Compile AI verification intent into deterministic executable semantics."""

    if intent_plan.module_name != hardware_spec.module_name:
        raise VerificationCompilationError(
            "MODULE_NAME_MISMATCH",
            f"Intent targets module '{intent_plan.module_name}' but HardwareSpec defines '{hardware_spec.module_name}'.",
        )

    supported_behaviors = derive_supported_behaviors(hardware_spec)
    compiled_cases: list[CompiledVerificationCase] = []
    existing_vectors: list[dict[str, int]] = []
    for index, intent_case in enumerate(intent_plan.cases):
        compiled_case = compile_intent_case(
            hardware_spec,
            intent_case,
            supported_behaviors,
            index,
            existing_vectors,
        )
        compiled_cases.append(compiled_case)
        if hardware_spec.design_type.value == "combinational":
            existing_vectors.append(extract_input_vector(compiled_case))
    compiled_cases.extend(
        synthesize_mandatory_semantic_feature_cases(
            hardware_spec=hardware_spec,
            existing_cases=compiled_cases,
        )
    )

    return CompiledVerificationPlan(
        module_name=hardware_spec.module_name,
        design_type=hardware_spec.design_type,
        strategy=intent_plan.strategy,
        cases=compiled_cases,
        coverage_targets=intent_plan.coverage_targets,
        assumptions=intent_plan.assumptions,
        notes=intent_plan.notes,
    )


def synthesize_mandatory_semantic_feature_cases(
    hardware_spec: HardwareSpec,
    existing_cases: list[CompiledVerificationCase],
) -> list[CompiledVerificationCase]:
    """Add deterministic minimum-coverage cases for preserved high-level semantic features."""

    if hardware_spec.design_type.value != "combinational":
        return []

    synthesized: list[CompiledVerificationCase] = []
    existing_vectors = [extract_input_vector(case) for case in existing_cases]
    existing_ids = {case.id for case in existing_cases}

    for feature in hardware_spec.semantic_features:
        if isinstance(feature, PrioritySelectFeature):
            synthesized.extend(
                build_priority_select_feature_cases(
                    hardware_spec=hardware_spec,
                    feature=feature,
                    existing_vectors=existing_vectors,
                    existing_ids=existing_ids,
                )
            )
        elif isinstance(feature, NonZeroFeature):
            synthesized.extend(
                build_nonzero_feature_cases(
                    hardware_spec=hardware_spec,
                    feature=feature,
                    existing_vectors=existing_vectors,
                    existing_ids=existing_ids,
                )
            )

    return synthesized


def compile_intent_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    supported_behaviors: set[str],
    case_index: int,
    existing_vectors: list[dict[str, int]] | None = None,
) -> CompiledVerificationCase:
    """Compile one intent case into deterministic actions and checks."""

    behavior = normalize_behavior_token(intent_case.target_behavior)
    scenario = normalize_scenario_token(intent_case.scenario)
    if behavior is None:
        raise VerificationCompilationError(
            "AMBIGUOUS_INTENT",
            f"Intent case '{intent_case.id}' uses unsupported behavior token '{intent_case.target_behavior}'.",
        )
    if scenario is None:
        scenario_behavior = normalize_behavior_token(intent_case.scenario)
        if scenario_behavior is not None:
            raise VerificationCompilationError(
                "INVALID_SCENARIO_VOCABULARY",
                (
                    f"Intent case '{intent_case.id}' uses semantic behavior token '{scenario_behavior}' in scenario. "
                    "scenario must use verification scenario vocabulary; semantic feature kinds belong in target_behavior."
                ),
            )
        raise VerificationCompilationError(
            "UNSUPPORTED_SCENARIO",
            f"Intent case '{intent_case.id}' uses unsupported scenario token '{intent_case.scenario}'.",
        )

    if behavior not in supported_behaviors and not (behavior == "ROUTING" and {"MUX", "ROUTING"} & supported_behaviors):
        raise VerificationCompilationError(
            "UNSUPPORTED_BEHAVIOR",
            f"Intent case '{intent_case.id}' requests behavior '{behavior}' that is not grounded in the HardwareSpec.",
        )

    sanitized_hints, hint_notes = sanitize_vector_hints(hardware_spec, intent_case)

    if hardware_spec.design_type.value == "combinational":
        actions, checks, provenance, notes = compile_combinational_case(
            hardware_spec,
            intent_case,
            behavior,
            sanitized_hints,
            case_index,
            existing_vectors or [],
        )
    else:
        actions, checks, provenance, notes = compile_sequential_case(
            hardware_spec,
            intent_case,
            behavior,
            scenario,
            sanitized_hints,
        )

    return CompiledVerificationCase(
        id=intent_case.id,
        name=intent_case.name,
        category=intent_case.category,
        target_behavior=behavior,
        scenario=scenario,
        priority=intent_case.priority,
        actions=actions,
        checks=checks,
        coverage_tags=intent_case.coverage_tags,
        state_provenance=provenance,
        compilation_notes=[*intent_case.notes, *hint_notes, *notes],
    )


def extract_input_vector(test_case: CompiledVerificationCase) -> dict[str, int]:
    """Extract the literal input assignments from one compiled case."""

    vector: dict[str, int] = {}
    for action in test_case.actions:
        if action.type != TestbenchActionType.SET_INPUT:
            continue

        assignment = action.assignment
        if assignment is None:
            raise VerificationCompilationError(
                "INVALID_TESTBENCH_ACTION",
                f"Compiled case '{test_case.id}' contains a SET_INPUT action without its required assignment payload.",
            )

        vector[assignment.signal] = assignment.value
    return vector


def build_priority_select_feature_cases(
    hardware_spec: HardwareSpec,
    feature: PrioritySelectFeature,
    existing_vectors: list[dict[str, int]],
    existing_ids: set[str],
) -> list[CompiledVerificationCase]:
    """Synthesize deterministic minimum-coverage cases for priority-selection semantics."""

    source_width = find_port_width(hardware_spec, feature.source_signal)
    if source_width < 1:
        return []

    low_index = 0
    high_index = source_width - 1
    obligations: list[tuple[str, int, str, object]] = [
        ("zero", 0, "zero-active priority input", is_zero_active_vector),
        ("low_boundary", 1 << low_index, "lowest-index one-hot priority input", is_low_boundary_one_hot_vector),
    ]
    if high_index != low_index:
        obligations.append(
            ("high_boundary", 1 << high_index, "highest-index one-hot priority input", is_high_boundary_one_hot_vector)
        )
        obligations.append(
            (
                "multi_active",
                (1 << low_index) | (1 << high_index),
                "multiple active source bits to verify deterministic priority winner",
                is_priority_competition_vector,
            )
        )

    synthesized: list[CompiledVerificationCase] = []
    for label, source_value, note, matcher in obligations:
        if any(matcher(vector, feature.source_signal, source_width) for vector in existing_vectors):
            continue
        synthesized.append(
            build_feature_case_from_source_value(
                hardware_spec=hardware_spec,
                case_id=unique_case_id(f"auto_priority_select_{label}", existing_ids),
                name=f"Deterministic priority-select coverage: {label.replace('_', ' ')}",
                category="FUNCTIONAL",
                target_behavior="PRIORITY_SELECT",
                scenario="BOUNDARY" if "boundary" in label else "BASIC",
                source_signal=feature.source_signal,
                source_value=source_value,
                coverage_tags=[
                    "deterministic semantic coverage",
                    f"priority_select:{feature.direction.value}",
                    label,
                ],
                compilation_note=note,
            )
        )
        existing_vectors.append(extract_input_vector(synthesized[-1]))
        existing_ids.add(synthesized[-1].id)

    return synthesized


def build_nonzero_feature_cases(
    hardware_spec: HardwareSpec,
    feature: NonZeroFeature,
    existing_vectors: list[dict[str, int]],
    existing_ids: set[str],
) -> list[CompiledVerificationCase]:
    """Synthesize deterministic minimum-coverage cases for NONZERO status semantics."""

    source_width = find_port_width(hardware_spec, feature.source_signal)
    nonzero_value = 1 if source_width >= 1 else 0
    synthesized: list[CompiledVerificationCase] = []

    required_cases = [
        ("zero", 0, "NONZERO source cleared to verify status deassertion", is_zero_active_vector),
        ("nonzero", nonzero_value, "NONZERO source asserted to verify status assertion", is_nonzero_vector),
    ]
    for label, source_value, note, matcher in required_cases:
        if any(matcher(vector, feature.source_signal, source_width) for vector in existing_vectors):
            continue
        synthesized.append(
            build_feature_case_from_source_value(
                hardware_spec=hardware_spec,
                case_id=unique_case_id(f"auto_nonzero_{label}", existing_ids),
                name=f"Deterministic NONZERO coverage: {label}",
                category="FUNCTIONAL",
                target_behavior="NONZERO",
                scenario="BASIC",
                source_signal=feature.source_signal,
                source_value=source_value,
                coverage_tags=["deterministic semantic coverage", "nonzero", label],
                compilation_note=note,
            )
        )
        existing_vectors.append(extract_input_vector(synthesized[-1]))
        existing_ids.add(synthesized[-1].id)

    return synthesized


def build_feature_case_from_source_value(
    hardware_spec: HardwareSpec,
    case_id: str,
    name: str,
    category: str,
    target_behavior: str,
    scenario: str,
    source_signal: str,
    source_value: int,
    coverage_tags: list[str],
    compilation_note: str,
) -> CompiledVerificationCase:
    """Build one deterministic feature-driven combinational coverage case."""

    combinational_semantics = require_combinational_semantics(
        hardware_spec,
        context=f"semantic-feature case '{case_id}'",
    )

    selected_inputs = {
        port.name: 0
        for port in hardware_spec.ports
        if port.direction == PortDirection.INPUT
        and (hardware_spec.clock is None or port.name != hardware_spec.clock.signal)
    }
    selected_inputs[source_signal] = source_value

    try:
        expected_values = evaluate_combinational_semantics(
            hardware_spec=hardware_spec,
            semantics=combinational_semantics,
            inputs=selected_inputs,
        )
    except SemanticEvaluationError as exc:
        raise VerificationCompilationError("UNRESOLVED_SEMANTICS", str(exc)) from exc

    actions = [set_input_action(signal_name, value) for signal_name, value in selected_inputs.items()]
    actions.append(settle_action())
    return CompiledVerificationCase(
        id=case_id,
        name=name,
        category=category,
        target_behavior=target_behavior,
        scenario=scenario,
        priority=1,
        actions=actions,
        checks=build_expected_checks_from_values(expected_values),
        coverage_tags=coverage_tags,
        state_provenance=[],
        compilation_notes=[compilation_note],
    )


def is_zero_active_vector(vector: dict[str, int], source_signal: str, source_width: int) -> bool:
    """Return True when the source vector drives no asserted bits."""

    return vector.get(source_signal) == 0


def is_nonzero_vector(vector: dict[str, int], source_signal: str, source_width: int) -> bool:
    """Return True when the source vector drives any asserted bit."""

    value = vector.get(source_signal)
    return value is not None and value != 0


def is_low_boundary_one_hot_vector(vector: dict[str, int], source_signal: str, source_width: int) -> bool:
    """Return True when the source vector is exactly the lowest-index one-hot value."""

    return vector.get(source_signal) == 1


def is_high_boundary_one_hot_vector(vector: dict[str, int], source_signal: str, source_width: int) -> bool:
    """Return True when the source vector is exactly the highest-index one-hot value."""

    return vector.get(source_signal) == (1 << (source_width - 1))


def is_priority_competition_vector(vector: dict[str, int], source_signal: str, source_width: int) -> bool:
    """Return True when the source vector contains at least two asserted bits."""

    value = vector.get(source_signal)
    if value is None or value == 0:
        return False
    masked = value & ((1 << source_width) - 1)
    return masked.bit_count() >= 2


def unique_case_id(base_id: str, existing_ids: set[str]) -> str:
    """Generate a stable unique compiled-case id without colliding with AI-authored ids."""

    if base_id not in existing_ids:
        return base_id
    suffix = 2
    while f"{base_id}_{suffix}" in existing_ids:
        suffix += 1
    return f"{base_id}_{suffix}"


def compile_combinational_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    vector_hints: dict[str, int],
    case_index: int,
    existing_vectors: list[dict[str, int]],
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    """Compile a combinational intent case."""

    if hardware_spec.semantics is not None and hardware_spec.semantics.combinational is not None:
        return compile_generic_combinational_case(
            hardware_spec,
            intent_case,
            behavior,
            vector_hints,
            case_index,
            existing_vectors,
        )

    if behavior in {"MUX", "ROUTING"}:
        return compile_mux_case(hardware_spec, intent_case, vector_hints, case_index)
    if behavior in {"ADD", "SUB", "AND", "OR"}:
        return compile_alu_case(hardware_spec, intent_case, behavior, vector_hints)
    if behavior == "DECODE":
        return compile_decoder_case(hardware_spec, intent_case, vector_hints, case_index)

    raise VerificationCompilationError(
        "UNSUPPORTED_BEHAVIOR",
        f"Intent case '{intent_case.id}' requested unsupported combinational behavior '{behavior}'.",
    )


def compile_generic_combinational_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    vector_hints: dict[str, int],
    case_index: int,
    existing_vectors: list[dict[str, int]],
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    """Compile one generic combinational intent case from structured semantic assignments."""

    combinational_semantics = require_combinational_semantics(
        hardware_spec,
        context=f"compiled intent case '{intent_case.id}'",
    )

    selected_inputs = choose_generic_combinational_inputs(
        hardware_spec=hardware_spec,
        intent_case=intent_case,
        behavior=behavior,
        vector_hints=vector_hints,
        case_index=case_index,
        existing_vectors=existing_vectors,
    )

    try:
        expected_values = evaluate_combinational_semantics(
            hardware_spec=hardware_spec,
            semantics=combinational_semantics,
            inputs=selected_inputs,
        )
    except SemanticEvaluationError as exc:
        raise VerificationCompilationError("UNRESOLVED_SEMANTICS", str(exc)) from exc

    actions = [set_input_action(signal_name, value) for signal_name, value in selected_inputs.items()]
    actions.append(settle_action())
    checks = build_expected_checks_from_values(expected_values)
    return actions, checks, ["generic combinational evaluation from structured semantic assignments"], []


def compile_sequential_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    scenario: str,
    vector_hints: dict[str, int],
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    """Compile a sequential intent case with deterministic known-state provenance."""

    if behavior == "RESET":
        return compile_reset_case(hardware_spec, intent_case)
    if behavior in {"SHIFT_LEFT", "SHIFT_RIGHT", "HOLD"} and infer_shift_direction(hardware_spec) is not None:
        return compile_shift_case(hardware_spec, intent_case, behavior, scenario, vector_hints)
    if behavior in {"INCREMENT", "DECREMENT", "HOLD", "WRAPAROUND"}:
        return compile_counter_case(hardware_spec, intent_case, behavior, scenario, vector_hints)

    raise VerificationCompilationError(
        "UNSUPPORTED_BEHAVIOR",
        f"Intent case '{intent_case.id}' requested unsupported sequential behavior '{behavior}'.",
    )


def require_combinational_semantics(
    hardware_spec: HardwareSpec,
    *,
    context: str,
):
    """Return combinational semantics or raise one structured deterministic failure."""

    semantics = hardware_spec.semantics
    if semantics is None or semantics.combinational is None:
        raise VerificationCompilationError(
            "MISSING_REQUIRED_SEMANTICS",
            f"HardwareSpec does not provide combinational semantics required for {context}.",
        )
    return semantics.combinational


def compile_mux_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    vector_hints: dict[str, int],
    case_index: int,
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    control_port = next((port for port in hardware_spec.ports if port.role == PortRole.CONTROL), None)
    output_port = next((port for port in hardware_spec.ports if port.direction == PortDirection.OUTPUT), None)
    data_inputs = [port for port in hardware_spec.ports if port.direction == PortDirection.INPUT and port.role == PortRole.DATA]
    if control_port is None or output_port is None or len(data_inputs) < 2:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "HardwareSpec does not define a resolvable mux interface.")

    select_value = vector_hints.get(control_port.name, case_index % len(sorted(data_inputs, key=lambda port: port.name)))

    sorted_inputs = sorted(data_inputs, key=lambda port: port.name)
    assignments: list[TestbenchAction] = []
    for index, port in enumerate(sorted_inputs):
        value = vector_hints.get(port.name)
        if value is None:
            value = 1 if index == select_value else 0
        assignments.append(set_input_action(port.name, value))

    assignments.append(set_input_action(control_port.name, select_value))
    selected_input = sorted_inputs[min(select_value, len(sorted_inputs) - 1)]
    checks = [ExpectedCheck(signal=output_port.name, reference_signal=selected_input.name)]
    return assignments + [settle_action()], checks, ["combinational routing from explicit control selection"], []


def compile_alu_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    vector_hints: dict[str, int],
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    required_ports = {"a", "b", "opcode", "result"}
    ports_by_name = {port.name: port for port in hardware_spec.ports}
    if not required_ports.issubset(ports_by_name):
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "HardwareSpec does not define the expected ALU ports.")

    a_value, b_value = choose_alu_operands(hardware_spec, behavior, intent_case.scenario, vector_hints)
    opcode_mapping = extract_alu_opcode_mapping(hardware_spec)
    opcode_value = resolve_opcode_for_behavior(hardware_spec, opcode_mapping, behavior)
    result_width = ports_by_name["result"].width
    expected_values = compute_unsigned_alu_outputs(hardware_spec, behavior, a_value, b_value, result_width)
    if not expected_values:
        raise VerificationCompilationError(
            "UNRESOLVED_REFERENCE",
            f"Intent case '{intent_case.id}' could not resolve deterministic ALU outputs for '{behavior}'.",
        )

    actions = [
        set_input_action("a", a_value),
        set_input_action("b", b_value),
        set_input_action("opcode", opcode_value),
        settle_action(),
    ]
    checks = build_expected_checks_from_values(expected_values)
    return actions, checks, ["combinational ALU evaluation from explicit operand hints"], []


def compile_decoder_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    vector_hints: dict[str, int],
    case_index: int,
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    input_ports = [port for port in hardware_spec.ports if port.direction == PortDirection.INPUT]
    output_ports = [port for port in hardware_spec.ports if port.direction == PortDirection.OUTPUT]
    if len(input_ports) != 1 or len(output_ports) != 1:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "HardwareSpec does not define a resolvable decoder interface.")

    input_port = input_ports[0]
    output_port = output_ports[0]
    input_domain = 1 << input_port.width
    input_value = vector_hints.get(input_port.name, case_index % input_domain)
    if input_value >= (1 << input_port.width):
        raise VerificationCompilationError(
            "MISSING_REQUIRED_SEMANTICS",
            f"Deterministic decoder input selection for '{intent_case.id}' produced an out-of-range value {input_value}.",
        )

    output_value = 1 << input_value
    actions = [set_input_action(input_port.name, input_value), settle_action()]
    checks = [ExpectedCheck(signal=output_port.name, value=output_value)]
    return actions, checks, ["combinational decoder mapping from explicit input hint"], []


def compile_reset_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    if hardware_spec.reset is None:
        raise VerificationCompilationError(
            "MISSING_REQUIRED_SEMANTICS",
            f"Intent case '{intent_case.id}' requests reset behavior but HardwareSpec does not define reset.",
        )

    actions, state = establish_reset_state(hardware_spec)
    checks = build_state_checks_from_reset(hardware_spec)
    return actions, checks, [state.provenance], []


def compile_counter_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    scenario: str,
    vector_hints: dict[str, int],
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    state_port = infer_single_state_output(hardware_spec)
    enable_port = infer_enable_signal(hardware_spec)
    if state_port is None or enable_port is None or hardware_spec.clock is None:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "HardwareSpec does not define resolvable counter semantics.")

    actions: list[TestbenchAction] = []
    provenance: list[str] = []
    notes: list[str] = []
    known_state: KnownState | None = None

    if behavior == "RESET":
        return compile_reset_case(hardware_spec, intent_case)

    actions, known_state = establish_reset_state(hardware_spec)
    provenance.append(known_state.provenance)
    actions.extend(deassert_reset_actions(hardware_spec))

    if behavior == "HOLD":
        prior_actions, known_state = establish_counter_step(
            hardware_spec,
            current_state=known_state,
            enable_value=1,
            edge_count=1,
        )
        actions.extend(prior_actions)
        provenance.append("known nonzero state established through one enabled active edge")
        actions.append(set_input_action(enable_port, 0))
        actions.append(active_edge_action())
        checks = [ExpectedCheck(signal=state_port.name, value=known_state.value)]
        return actions, checks, provenance, notes

    if behavior in {"INCREMENT", "DECREMENT"}:
        edge_count = intent_case.edge_count_hint or 1
        actions.append(set_input_action(enable_port, 1))
        actions.append(repeat_active_edges_action(edge_count) if edge_count > 1 else active_edge_action())
        next_state = propagate_counter_state(hardware_spec, known_state.value, edge_count, enable_value=1)
        checks = [ExpectedCheck(signal=state_port.name, value=next_state)]
        provenance.append(f"state propagated deterministically across {edge_count} active edge(s)")
        return actions, checks, provenance, notes

    if behavior == "WRAPAROUND":
        modulus = 1 << state_port.width
        boundary_value = modulus - 1
        if boundary_value > 0:
            actions.append(set_input_action(enable_port, 1))
            actions.append(repeat_active_edges_action(boundary_value))
        actions.append(active_edge_action())
        checks = [ExpectedCheck(signal=state_port.name, value=0)]
        provenance.append("boundary state established legally from reset through enabled active edges")
        return actions, checks, provenance, notes

    raise VerificationCompilationError(
        "UNSUPPORTED_BEHAVIOR",
        f"Intent case '{intent_case.id}' requested unsupported counter behavior '{behavior}'.",
    )


def compile_shift_case(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    scenario: str,
    vector_hints: dict[str, int],
) -> tuple[list[TestbenchAction], list[ExpectedCheck], list[str], list[str]]:
    state_signal = infer_shift_state_output(hardware_spec)
    serial_signal = infer_serial_input_signal(hardware_spec)
    enable_port = infer_enable_signal(hardware_spec)
    direction = infer_shift_direction(hardware_spec)
    if state_signal is None or serial_signal is None or enable_port is None or direction is None:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "HardwareSpec does not define resolvable shift-register semantics.")

    actions, known_state = establish_reset_state(hardware_spec)
    provenance = [known_state.provenance]
    notes: list[str] = []
    actions.extend(deassert_reset_actions(hardware_spec))

    if behavior == "HOLD":
        serial_value = vector_hints.get(serial_signal, 1)
        actions.append(set_input_action(enable_port, 1))
        actions.append(set_input_action(serial_signal, serial_value))
        actions.append(active_edge_action())
        established_state = compute_shift_next_state(known_state.value, serial_value, find_port_width(hardware_spec, state_signal), direction)
        actions.append(set_input_action(enable_port, 0))
        actions.append(active_edge_action())
        checks = [ExpectedCheck(signal=state_signal, value=established_state)]
        provenance.append("known state established through one enabled legal shift before hold check")
        return actions, checks, provenance, notes

    if behavior in {"SHIFT_LEFT", "SHIFT_RIGHT"}:
        serial_value = vector_hints.get(serial_signal, 1)
        edge_count = intent_case.edge_count_hint or (4 if scenario == "ENABLED_MULTI_EDGE" else 1)
        actions.append(set_input_action(enable_port, 1))
        actions.append(set_input_action(serial_signal, serial_value))
        actions.append(repeat_active_edges_action(edge_count) if edge_count > 1 else active_edge_action())

        state_width = find_port_width(hardware_spec, state_signal)
        next_state = known_state.value
        for _ in range(edge_count):
            next_state = compute_shift_next_state(next_state, serial_value, state_width, direction)
        checks = [ExpectedCheck(signal=state_signal, value=next_state)]
        provenance.append(f"state propagated deterministically across {edge_count} shift edge(s)")
        return actions, checks, provenance, notes

    raise VerificationCompilationError(
        "UNSUPPORTED_BEHAVIOR",
        f"Intent case '{intent_case.id}' requested unsupported shift-register behavior '{behavior}'.",
    )


def establish_reset_state(hardware_spec: HardwareSpec) -> tuple[list[TestbenchAction], KnownState]:
    """Establish one deterministic known state via reset semantics."""

    if hardware_spec.reset is None:
        raise VerificationCompilationError(
            "UNESTABLISHED_SEQUENTIAL_STATE",
            "Sequential state cannot be established because HardwareSpec does not define reset semantics.",
        )

    state_port = infer_single_state_output(hardware_spec)
    if state_port is None:
        raise VerificationCompilationError(
            "MISSING_REQUIRED_SEMANTICS",
            "Sequential reset establishment requires one resolvable observable state output.",
        )

    reset_value = extract_reset_value(hardware_spec, state_port.name)
    if reset_value is None:
        raise VerificationCompilationError(
            "MISSING_REQUIRED_SEMANTICS",
            f"Reset value for '{state_port.name}' is not defined in HardwareSpec.reset.reset_values.",
        )

    active_reset = active_reset_value(hardware_spec)
    actions = [set_input_action(hardware_spec.reset.signal, active_reset)]
    if hardware_spec.reset.type == ResetType.SYNCHRONOUS:
        actions.append(active_edge_action())
    else:
        actions.append(settle_action())

    return actions, KnownState(
        signal=state_port.name,
        value=reset_value,
        provenance=f"{hardware_spec.reset.type.value} reset assertion established known state {state_port.name}={reset_value}",
    )


def deassert_reset_actions(hardware_spec: HardwareSpec) -> list[TestbenchAction]:
    """Return actions that place reset back into its inactive state when defined."""

    if hardware_spec.reset is None:
        return []
    return [set_input_action(hardware_spec.reset.signal, inactive_reset_value(hardware_spec))]


def establish_counter_step(
    hardware_spec: HardwareSpec,
    current_state: KnownState,
    enable_value: int,
    edge_count: int,
) -> tuple[list[TestbenchAction], KnownState]:
    """Propagate a counter state deterministically through a known number of edges."""

    enable_port = infer_enable_signal(hardware_spec)
    if enable_port is None:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "Counter semantics require an enable signal.")

    actions = [set_input_action(enable_port, enable_value)]
    actions.append(repeat_active_edges_action(edge_count) if edge_count > 1 else active_edge_action())
    next_value = propagate_counter_state(hardware_spec, current_state.value, edge_count, enable_value)
    state_signal = infer_single_state_output(hardware_spec)
    assert state_signal is not None
    return actions, KnownState(signal=state_signal.name, value=next_value, provenance="counter propagated from known state")


def propagate_counter_state(
    hardware_spec: HardwareSpec,
    current_value: int,
    edge_count: int,
    enable_value: int,
) -> int:
    """Propagate a simple fixed-width counter state deterministically."""

    state_port = infer_single_state_output(hardware_spec)
    if state_port is None:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "Counter state output is not resolvable.")

    if enable_value == 0:
        return current_value

    modulus = 1 << state_port.width
    direction = "down" if "DECREMENT" in derive_supported_behaviors(hardware_spec) else "up"
    if direction == "down":
        return (current_value - edge_count) % modulus
    return (current_value + edge_count) % modulus


def resolve_opcode_for_behavior(
    hardware_spec: HardwareSpec,
    opcode_mapping: dict[str, str],
    behavior: str,
) -> int:
    """Resolve the opcode integer for one structured ALU behavior."""

    opcode_port = next((port for port in hardware_spec.ports if port.name == "opcode"), None)
    if opcode_port is None:
        raise VerificationCompilationError("MISSING_REQUIRED_SEMANTICS", "HardwareSpec does not define an opcode port.")

    for token, operation in opcode_mapping.items():
        if operation == behavior:
            resolved = normalize_opcode_token(token, opcode_port.width)
            if resolved is None:
                break
            return int(resolved, 2)

    raise VerificationCompilationError(
        "UNRESOLVED_REFERENCE",
        f"HardwareSpec does not define an unambiguous opcode mapping for behavior '{behavior}'.",
    )


def build_expected_checks_from_values(expected_values: dict[str, int | str]) -> list[ExpectedCheck]:
    """Convert deterministic expected values into literal checks."""

    checks: list[ExpectedCheck] = []
    for signal, value in expected_values.items():
        if isinstance(value, int):
            checks.append(ExpectedCheck(signal=signal, value=value))
    return checks


def build_state_checks_from_reset(hardware_spec: HardwareSpec) -> list[ExpectedCheck]:
    """Build expected reset-state checks from HardwareSpec.reset.reset_values."""

    checks: list[ExpectedCheck] = []
    assert hardware_spec.reset is not None
    for signal, value in hardware_spec.reset.reset_values.items():
        parsed = value if isinstance(value, int) else parse_numeric_literal(str(value))
        if parsed is None:
            raise VerificationCompilationError(
                "UNRESOLVED_REFERENCE",
                f"Reset value for '{signal}' is not a resolvable integer literal.",
            )
        checks.append(ExpectedCheck(signal=signal, value=parsed))
    return checks


def parse_signal_hint(
    hardware_spec: HardwareSpec,
    signal_name: str,
    value: int | str | bool | None,
) -> int | None:
    """Parse one signal-aware vector hint into a canonical integer."""

    if value is None:
        return None

    port = next((candidate for candidate in hardware_spec.ports if candidate.name == signal_name), None)
    if port is None:
        raise VerificationCompilationError("UNKNOWN_SIGNAL", f"Unknown signal '{signal_name}' in vector hints.")

    if isinstance(value, bool):
        numeric = 1 if value else 0
    elif isinstance(value, int):
        numeric = value
    else:
        stripped = value.strip()
        if not stripped:
            return None

        if signal_name in derive_control_mapping_signals(hardware_spec):
            mapped = normalize_opcode_token(stripped, port.width)
            if mapped is not None and mapped in extract_alu_opcode_mapping(hardware_spec):
                numeric = int(mapped, 2)
            else:
                parsed = parse_numeric_literal(stripped)
                if parsed is None:
                    return None
                numeric = parsed
        else:
            if stripped.lower().startswith("0b"):
                numeric = int(stripped[2:], 2)
            else:
                parsed = parse_numeric_literal(stripped)
                if parsed is None:
                    return None
                numeric = parsed

    validate_fits_width(signal_name, port.width, numeric)
    return numeric


def derive_control_mapping_signals(hardware_spec: HardwareSpec) -> set[str]:
    """Return signals whose bare token hints may use structured control encodings."""

    opcode_mapping = extract_alu_opcode_mapping(hardware_spec)
    if opcode_mapping:
        return {"opcode"}
    return set()


def validate_fits_width(signal_name: str, width: int, value: int) -> None:
    """Reject out-of-range deterministic values before rendering."""

    if value < 0 or value > ((1 << width) - 1):
        raise VerificationCompilationError(
            "INVALID_VECTOR_HINT",
            f"Signal '{signal_name}' value {value} does not fit in {width} bits.",
        )


def sanitize_vector_hints(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
) -> tuple[dict[str, int], list[str]]:
    """Sanitize optional AI vector hints into safe deterministic advisory values."""

    sanitized: dict[str, int] = {}
    notes: list[str] = []
    input_ports = {port.name: port for port in hardware_spec.ports if port.direction == PortDirection.INPUT}
    output_names = {port.name for port in hardware_spec.ports if port.direction == PortDirection.OUTPUT}
    clock_name = hardware_spec.clock.signal if hardware_spec.clock is not None else None

    for signal_name, raw_value in intent_case.vector_hints.items():
        if signal_name == clock_name:
            notes.append(
                f"ignored AI vector hint {signal_name}={raw_value}: clock timing belongs to deterministic compilation"
            )
            continue
        if signal_name in output_names:
            notes.append(f"ignored AI vector hint for output/state {signal_name}")
            continue
        if signal_name not in input_ports:
            notes.append(f"ignored AI vector hint {signal_name}={raw_value}: not a valid DUT input")
            continue

        try:
            parsed_value = parse_signal_hint(hardware_spec, signal_name, raw_value)
        except VerificationCompilationError as exc:
            notes.append(f"ignored invalid AI vector hint {signal_name}={raw_value}: {exc.message}")
            continue

        if parsed_value is None:
            notes.append(f"ignored invalid AI vector hint {signal_name}={raw_value}: could not parse value safely")
            continue

        sanitized[signal_name] = parsed_value

    return sanitized, notes


def choose_alu_operands(
    hardware_spec: HardwareSpec,
    behavior: str,
    scenario: str,
    vector_hints: dict[str, int],
) -> tuple[int, int]:
    """Choose deterministic legal ALU operands, using AI hints only when valid."""

    a_width = find_port_width(hardware_spec, "a")
    b_width = find_port_width(hardware_spec, "b")
    if a_width != b_width:
        raise VerificationCompilationError(
            "MISSING_REQUIRED_SEMANTICS",
            "Deterministic ALU operand selection requires matching operand widths.",
        )

    width = a_width
    mask = (1 << width) - 1
    alternating_high = build_alternating_pattern(width, start_with_one=True)
    alternating_low = build_alternating_pattern(width, start_with_one=False)

    default_pairs: dict[str, tuple[int, int]] = {
        "ADD": (mask, 1) if normalize_scenario_token(scenario) == "BOUNDARY" else (2, 3),
        "SUB": (0, mask) if normalize_scenario_token(scenario) == "BOUNDARY" else (mask, 1),
        "AND": (alternating_high, alternating_low),
        "OR": (alternating_high, alternating_low),
    }
    default_a, default_b = default_pairs.get(behavior, (1, 0))
    default_a &= mask
    default_b &= mask

    return (
        vector_hints.get("a", default_a),
        vector_hints.get("b", default_b),
    )


def build_alternating_pattern(width: int, start_with_one: bool) -> int:
    """Build one width-aware alternating-bit pattern."""

    bits = ["1" if ((index % 2 == 0) == start_with_one) else "0" for index in range(width)]
    return int("".join(bits), 2) if bits else 0


def choose_generic_combinational_inputs(
    hardware_spec: HardwareSpec,
    intent_case: VerificationIntentCase,
    behavior: str,
    vector_hints: dict[str, int],
    case_index: int,
    existing_vectors: list[dict[str, int]],
) -> dict[str, int]:
    """Choose deterministic legal combinational inputs, using valid hints only as advisory."""

    input_ports = [
        port
        for port in hardware_spec.ports
        if port.direction == PortDirection.INPUT
        and (hardware_spec.clock is None or port.name != hardware_spec.clock.signal)
    ]
    selected = {signal: value for signal, value in vector_hints.items()}
    protected_signals = set(vector_hints)

    required_controls = infer_required_semantic_controls(hardware_spec, behavior)
    for signal_name, control_value in required_controls.items():
        selected.setdefault(signal_name, control_value)
    protected_signals.update(required_controls)

    if behavior == "PRIORITY_SELECT":
        apply_priority_select_vector_strategy(hardware_spec, selected, case_index)
    elif behavior == "NONZERO":
        apply_nonzero_vector_strategy(hardware_spec, selected, case_index)
    elif behavior in {"EQ", "NE", "LT", "LE", "GT", "GE", "COMPARE"}:
        apply_comparison_vector_strategy(hardware_spec, behavior, selected, case_index)
    elif behavior in {"ROUTING", "MUX", "MAPPING"}:
        apply_routing_vector_strategy(hardware_spec, selected, case_index)
    elif behavior in {"ADD", "SUB", "BIT_AND", "BIT_OR", "BIT_XOR", "AND", "OR"}:
        apply_logic_arithmetic_vector_strategy(hardware_spec, behavior, selected, case_index)
    elif input_domain_size(input_ports) <= 16:
        for signal_name, value in exhaustive_case_assignment(input_ports, case_index).items():
            selected.setdefault(signal_name, value)

    for index, port in enumerate(input_ports):
        selected.setdefault(port.name, representative_value_for_input(port.width, case_index + index))

    avoid_duplicate_combinational_vector(
        input_ports=input_ports,
        selected=selected,
        protected_signals=protected_signals,
        existing_vectors=existing_vectors,
        case_index=case_index,
    )

    return {port.name: selected[port.name] for port in input_ports}


def apply_priority_select_vector_strategy(
    hardware_spec: HardwareSpec,
    selected: dict[str, int],
    case_index: int,
) -> None:
    """Choose deterministic vectors that exercise preserved priority-selection semantics when no explicit hint exists."""

    feature = next((feature for feature in hardware_spec.semantic_features if isinstance(feature, PrioritySelectFeature)), None)
    if feature is None:
        return
    if feature.source_signal in selected:
        return

    width = find_port_width(hardware_spec, feature.source_signal)
    if width < 1:
        return

    low = 0
    high = width - 1
    candidates = [0, 1 << low]
    if high != low:
        candidates.extend([1 << high, (1 << low) | (1 << high)])

    selected[feature.source_signal] = candidates[case_index % len(candidates)]


def apply_nonzero_vector_strategy(
    hardware_spec: HardwareSpec,
    selected: dict[str, int],
    case_index: int,
) -> None:
    """Choose deterministic vectors that exercise preserved NONZERO semantics when no explicit hint exists."""

    feature = next((feature for feature in hardware_spec.semantic_features if isinstance(feature, NonZeroFeature)), None)
    if feature is None:
        return
    if feature.source_signal in selected:
        return

    selected[feature.source_signal] = 0 if case_index % 2 == 0 else 1


def infer_required_semantic_controls(hardware_spec: HardwareSpec, behavior: str) -> dict[str, int]:
    """Infer simple control assignments needed to reach one AST capability under SelectExpr branches."""

    if hardware_spec.semantics is None or hardware_spec.semantics.combinational is None:
        return {}
    if behavior in {"FUNCTIONAL", "MAPPING", "ROUTING", "MUX", "COMPARE"}:
        return {}

    matches = find_capability_path_matches(hardware_spec, behavior)
    if not matches:
        return {}

    resolved_matches = [match.assignments for match in matches if not match.unresolved_path]
    if resolved_matches:
        return dict(sorted(resolved_matches[0].items()))

    raise VerificationCompilationError(
        "UNRESOLVED_SEMANTIC_PATH",
        f"HardwareSpec semantics contain behavior '{behavior}', but the compiler could not derive a supported deterministic control path to reach it.",
    )


def apply_comparison_vector_strategy(
    hardware_spec: HardwareSpec,
    behavior: str,
    selected: dict[str, int],
    case_index: int,
) -> None:
    """Choose a deterministic comparison-friendly vector for two-input comparators."""

    data_inputs = [port for port in hardware_spec.ports if port.direction == PortDirection.INPUT and port.role == PortRole.DATA]
    if len(data_inputs) < 2:
        return
    first = data_inputs[0]
    second = data_inputs[1]
    max_value = (1 << min(first.width, second.width)) - 1
    eq_value = comparison_seed_values(max_value, case_index)
    if behavior == "EQ":
        selected.setdefault(first.name, eq_value)
        selected.setdefault(second.name, selected.get(first.name, eq_value))
    elif behavior == "NE":
        selected.setdefault(first.name, 0)
        selected.setdefault(second.name, distinct_value(selected[first.name], max_value, case_index))
    elif behavior == "GT":
        selected.setdefault(second.name, 1 if max_value >= 1 else 0)
        selected.setdefault(first.name, greater_than_value(selected[second.name], max_value, case_index))
    elif behavior == "GE":
        ge_value = comparison_seed_values(max_value, case_index)
        selected.setdefault(first.name, ge_value)
        selected.setdefault(second.name, ge_value)
    elif behavior == "LT":
        selected.setdefault(first.name, 1 if max_value >= 1 else 0)
        selected.setdefault(second.name, greater_than_value(selected[first.name], max_value, case_index))
    elif behavior == "LE":
        le_value = comparison_seed_values(max_value, case_index)
        selected.setdefault(first.name, le_value)
        selected.setdefault(second.name, le_value)


def apply_routing_vector_strategy(
    hardware_spec: HardwareSpec,
    selected: dict[str, int],
    case_index: int,
) -> None:
    """Choose deterministic routing-friendly control and data values."""

    control_ports = [port for port in hardware_spec.ports if port.direction == PortDirection.INPUT and port.role == PortRole.CONTROL]
    data_inputs = [port for port in hardware_spec.ports if port.direction == PortDirection.INPUT and port.role == PortRole.DATA]
    for control_port in control_ports:
        selected.setdefault(control_port.name, case_index % (1 << control_port.width))
    for index, data_port in enumerate(data_inputs):
        max_value = (1 << data_port.width) - 1
        candidates = [max_value if index % 2 == 0 else 0, representative_value_for_input(data_port.width, case_index + index)]
        for candidate in candidates:
            if data_port.name not in selected:
                selected[data_port.name] = candidate
                break


def apply_logic_arithmetic_vector_strategy(
    hardware_spec: HardwareSpec,
    behavior: str,
    selected: dict[str, int],
    case_index: int,
) -> None:
    """Choose deterministic legal arithmetic/logic operand values."""

    data_inputs = [port for port in hardware_spec.ports if port.direction == PortDirection.INPUT and port.role == PortRole.DATA]
    if len(data_inputs) < 2:
        return
    first = data_inputs[0]
    second = data_inputs[1]
    max_value = (1 << min(first.width, second.width)) - 1
    midpoint = max_value // 2
    one = 1 if max_value >= 1 else 0
    two = 2 if max_value >= 2 else one
    add_pairs = [
        (max_value, one),
        (midpoint, midpoint),
        (two, 3 if max_value >= 3 else one),
        (build_alternating_pattern(first.width, True), one),
    ]
    sub_pairs = [
        (0, max_value),
        (max_value, one),
        (midpoint, one),
        (two, one),
    ]
    if behavior in {"ADD"}:
        preferred_first, preferred_second = add_pairs[case_index % len(add_pairs)]
        selected.setdefault(first.name, preferred_first)
        selected.setdefault(second.name, preferred_second)
    elif behavior in {"SUB"}:
        preferred_first, preferred_second = sub_pairs[case_index % len(sub_pairs)]
        selected.setdefault(first.name, preferred_first)
        selected.setdefault(second.name, preferred_second)
    elif behavior in {"BIT_AND", "AND"}:
        selected.setdefault(first.name, build_alternating_pattern(first.width, True))
        selected.setdefault(second.name, build_alternating_pattern(second.width, False))
    elif behavior in {"BIT_OR", "OR"}:
        selected.setdefault(first.name, build_alternating_pattern(first.width, True))
        selected.setdefault(second.name, build_alternating_pattern(second.width, False))
    elif behavior == "BIT_XOR":
        selected.setdefault(first.name, build_alternating_pattern(first.width, True))
        selected.setdefault(second.name, build_alternating_pattern(second.width, True))


def representative_value_for_input(width: int, salt: int) -> int:
    """Choose one deterministic representative value for an input width."""

    max_value = (1 << width) - 1
    candidates = [0, 1 if max_value >= 1 else 0, max_value]
    if width > 1:
        candidates.append(max_value // 2)
        candidates.append(build_alternating_pattern(width, True))
    unique_candidates = []
    for candidate in candidates:
        if candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates[salt % len(unique_candidates)]


def candidate_values_for_input(width: int, salt: int) -> list[int]:
    """Return deterministic legal candidate values for one input width."""

    max_value = (1 << width) - 1
    candidates = [0, 1 if max_value >= 1 else 0, max_value]
    if width > 1:
        candidates.extend(
            [
                max_value // 2,
                build_alternating_pattern(width, True),
                build_alternating_pattern(width, False),
            ]
        )
    ordered: list[int] = []
    seen: set[int] = set()
    for offset in range(len(candidates)):
        candidate = candidates[(salt + offset) % len(candidates)]
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def avoid_duplicate_combinational_vector(
    *,
    input_ports: list[object],
    selected: dict[str, int],
    protected_signals: set[str],
    existing_vectors: list[dict[str, int]],
    case_index: int,
) -> None:
    """Prefer a non-duplicate legal vector when deterministic alternatives exist."""

    current_vector = {port.name: selected[port.name] for port in input_ports}
    if current_vector not in existing_vectors:
        return

    adjustable_ports = [port for port in input_ports if port.name not in protected_signals]
    for port_index, port in enumerate(adjustable_ports):
        original_value = selected[port.name]
        for candidate in candidate_values_for_input(port.width, case_index + port_index):
            if candidate == original_value:
                continue
            trial = dict(current_vector)
            trial[port.name] = candidate
            if trial not in existing_vectors:
                selected[port.name] = candidate
                return

    if len(adjustable_ports) < 2:
        return

    first_port, second_port = adjustable_ports[0], adjustable_ports[1]
    for first_candidate in candidate_values_for_input(first_port.width, case_index):
        for second_candidate in candidate_values_for_input(second_port.width, case_index + 1):
            trial = dict(current_vector)
            trial[first_port.name] = first_candidate
            trial[second_port.name] = second_candidate
            if trial == current_vector:
                continue
            if trial not in existing_vectors:
                selected[first_port.name] = first_candidate
                selected[second_port.name] = second_candidate
                return


def comparison_seed_values(max_value: int, case_index: int) -> int:
    """Choose one deterministic comparison seed value."""

    if max_value <= 0:
        return 0
    seeds = [1, min(2, max_value), max_value // 2, max_value]
    unique = []
    for seed in seeds:
        if seed not in unique:
            unique.append(seed)
    return unique[case_index % len(unique)]


def distinct_value(current_value: int, max_value: int, case_index: int) -> int:
    """Choose one deterministic legal value distinct from the current value when possible."""

    for candidate in candidate_values_for_input(max(1, max_value.bit_length()), case_index):
        if candidate <= max_value and candidate != current_value:
            return candidate
    return current_value


def greater_than_value(base_value: int, max_value: int, case_index: int) -> int:
    """Choose one deterministic legal value greater than the supplied base when possible."""

    candidates = [value for value in candidate_values_for_input(max(1, max_value.bit_length()), case_index) if value <= max_value]
    for candidate in candidates:
        if candidate > base_value:
            return candidate
    return min(max_value, base_value)


def input_domain_size(input_ports: list[object]) -> int:
    """Return the total combinational input domain size."""

    size = 1
    for port in input_ports:
        size *= 1 << port.width
    return size


def exhaustive_case_assignment(input_ports: list[object], case_index: int) -> dict[str, int]:
    """Choose one deterministic assignment by enumerating the small input domain."""

    remainder = case_index
    assignments: dict[str, int] = {}
    for port in reversed(input_ports):
        domain = 1 << port.width
        assignments[port.name] = remainder % domain
        remainder //= domain
    return assignments


def infer_enable_signal(hardware_spec: HardwareSpec) -> str | None:
    """Return a likely enable/control signal when one is clearly present."""

    for port in hardware_spec.ports:
        if port.direction == PortDirection.INPUT and port.name.lower() == "en":
            return port.name
    for port in hardware_spec.ports:
        if port.direction == PortDirection.INPUT and port.role == PortRole.CONTROL:
            return port.name
    return None


def infer_single_state_output(hardware_spec: HardwareSpec):
    """Return one resolvable observable state/output port when unique."""

    outputs = [port for port in hardware_spec.ports if port.direction == PortDirection.OUTPUT]
    return outputs[0] if len(outputs) == 1 else None


def find_port_width(hardware_spec: HardwareSpec, signal_name: str) -> int:
    """Return the width of one named port."""

    port = next((candidate for candidate in hardware_spec.ports if candidate.name == signal_name), None)
    if port is None:
        raise VerificationCompilationError("UNKNOWN_SIGNAL", f"Unknown signal '{signal_name}'.")
    return port.width


def extract_reset_value(hardware_spec: HardwareSpec, signal_name: str) -> int | None:
    """Return one integer reset value for the chosen signal when defined."""

    assert hardware_spec.reset is not None
    raw_value = hardware_spec.reset.reset_values.get(signal_name)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str):
        return parse_numeric_literal(raw_value)
    return None


def active_reset_value(hardware_spec: HardwareSpec) -> int:
    """Return the numeric asserted value for the configured reset polarity."""

    assert hardware_spec.reset is not None
    return 1 if hardware_spec.reset.polarity == ResetPolarity.ACTIVE_HIGH else 0


def inactive_reset_value(hardware_spec: HardwareSpec) -> int:
    """Return the numeric inactive value for the configured reset polarity."""

    assert hardware_spec.reset is not None
    return 0 if hardware_spec.reset.polarity == ResetPolarity.ACTIVE_HIGH else 1


def set_input_action(signal: str, value: int) -> TestbenchAction:
    """Construct one deterministic input assignment action."""

    return TestbenchAction(type=TestbenchActionType.SET_INPUT, assignment=InputAssignment(signal=signal, value=value))


def active_edge_action() -> TestbenchAction:
    """Construct one active-edge action."""

    return TestbenchAction(type=TestbenchActionType.ACTIVE_CLOCK_EDGE)


def repeat_active_edges_action(count: int) -> TestbenchAction:
    """Construct one repeated-active-edges action."""

    return TestbenchAction(type=TestbenchActionType.REPEAT_ACTIVE_EDGES, count=count)


def settle_action() -> TestbenchAction:
    """Construct one settle action."""

    return TestbenchAction(type=TestbenchActionType.SETTLE)
