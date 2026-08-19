import re
from dataclasses import dataclass

from rtl_assistant.models.hardware_spec import DesignType, HardwareSpec, PortRole, ResetType
from rtl_assistant.models.reference import (
    ReferenceResolution,
    ReferenceResolutionStatus,
)
from rtl_assistant.models.verification_plan import VerificationTestCase
from rtl_assistant.reference.base import ReferenceResolver
from rtl_assistant.reference.handlers.alu import (
    compute_unsigned_alu_outputs,
    extract_alu_literal_vector,
    extract_alu_stimulus_vector,
    resolve_alu_operation_from_vector,
)


@dataclass(slots=True)
class PortView:
    """Small helper view for looking up port properties."""

    name: str
    width: int
    role: str
    direction: str
    signed: bool


class DeterministicReferenceResolver(ReferenceResolver):
    """Aggregate deterministic reference resolvers behind one stable interface."""

    def __init__(self, resolvers: list[ReferenceResolver] | None = None) -> None:
        self._resolvers = resolvers or [
            UnsignedFixedWidthALUResolver(),
            SelectRoutingResolver(),
            OneHotDecoderResolver(),
            FixedWidthCounterResolver(),
        ]

    def can_resolve(self, hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool:
        """Return True when any registered resolver can safely handle the test case."""

        return any(resolver.can_resolve(hardware_spec, test_case) for resolver in self._resolvers)

    def resolve(
        self,
        hardware_spec: HardwareSpec,
        test_case: VerificationTestCase,
    ) -> ReferenceResolution:
        """Resolve expected values with the first matching deterministic handler."""

        for resolver in self._resolvers:
            if resolver.can_resolve(hardware_spec, test_case):
                return resolver.resolve(hardware_spec, test_case)

        return ReferenceResolution(
            status=ReferenceResolutionStatus.UNSUPPORTED,
            resolver="unsupported_reference_semantics",
            expected_values={},
            canonical_expected=[],
            explanation="HardwareSpec semantics were not safely resolvable by the deterministic handlers.",
            error_type=None,
            error_message=None,
        )


class UnsignedFixedWidthALUResolver(ReferenceResolver):
    """Resolve simple fixed-width unsigned ALU expectations from explicit test vectors."""

    resolver_name = "unsigned_fixed_width_alu"

    def can_resolve(self, hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool:
        port_names = {port.name.lower() for port in hardware_spec.ports}
        required_ports = {"a", "b", "opcode", "result"}
        if not required_ports.issubset(port_names):
            return False

        vector = extract_alu_stimulus_vector(hardware_spec, test_case)
        if vector.a is None or vector.b is None or vector.opcode_token is None:
            return False

        return resolve_alu_operation_from_vector(hardware_spec, vector) is not None

    def resolve(
        self,
        hardware_spec: HardwareSpec,
        test_case: VerificationTestCase,
    ) -> ReferenceResolution:
        vector = extract_alu_stimulus_vector(hardware_spec, test_case)
        a_value = vector.a
        b_value = vector.b
        operation = resolve_alu_operation_from_vector(hardware_spec, vector)
        result_port = find_port(hardware_spec, "result")

        if not isinstance(a_value, int) or not isinstance(b_value, int) or operation is None or result_port is None:
            return unsupported_resolution(
                self.resolver_name,
                "ALU operands, opcode mapping, result width, or operation could not be determined safely.",
            )

        expected_values = compute_alu_expected_values(
            hardware_spec=hardware_spec,
            operation=operation,
            a_value=a_value,
            b_value=b_value,
            width=result_port.width,
        )
        if not expected_values:
            return unsupported_resolution(
                self.resolver_name,
                "ALU operation could not be resolved into deterministic expected outputs.",
            )

        return resolved_resolution(
            hardware_spec=hardware_spec,
            resolver_name=self.resolver_name,
            expected_values=expected_values,
            explanation=f"Computed {operation} deterministically from explicit operand literals and HardwareSpec widths.",
        )


class SelectRoutingResolver(ReferenceResolver):
    """Resolve simple combinational select-routing expectations such as mux behavior."""

    resolver_name = "select_routing"

    def can_resolve(self, hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool:
        if hardware_spec.design_type != DesignType.COMBINATIONAL:
            return False

        output_ports = get_ports_by_direction(hardware_spec, "output")
        if len(output_ports) != 1:
            return False

        control_port = find_control_port(hardware_spec)
        data_inputs = [
            port for port in get_ports_by_direction(hardware_spec, "input") if port.role == PortRole.DATA.value
        ]
        if control_port is None or len(data_inputs) < 2:
            return False

        if derive_select_mapping(hardware_spec, control_port.name, output_ports[0].name, data_inputs) is None:
            return False

        assignments = extract_signal_values(
            [*test_case.setup, *test_case.stimulus],
            {control_port.name, *(port.name for port in data_inputs)},
        )
        return control_port.name in assignments

    def resolve(
        self,
        hardware_spec: HardwareSpec,
        test_case: VerificationTestCase,
    ) -> ReferenceResolution:
        output_port = get_ports_by_direction(hardware_spec, "output")[0]
        control_port = find_control_port(hardware_spec)
        data_inputs = [
            port for port in get_ports_by_direction(hardware_spec, "input") if port.role == PortRole.DATA.value
        ]

        if control_port is None:
            return unsupported_resolution(self.resolver_name, "Control port could not be identified safely.")

        mapping = derive_select_mapping(hardware_spec, control_port.name, output_port.name, data_inputs)
        if mapping is None:
            return unsupported_resolution(
                self.resolver_name,
                "Routing behavior could not be derived safely from the HardwareSpec rules.",
            )

        assignments = extract_signal_values(
            [*test_case.setup, *test_case.stimulus],
            {control_port.name, *(port.name for port in data_inputs)},
        )
        select_value = assignments.get(control_port.name)
        if not isinstance(select_value, int):
            return unsupported_resolution(self.resolver_name, "Select literal was not available as an integer value.")

        selected_input_name = mapping.get(select_value)
        if selected_input_name is None:
            return unsupported_resolution(
                self.resolver_name,
                "Select literal did not map to a known routed input in the HardwareSpec.",
            )

        selected_value = assignments.get(selected_input_name)
        if not isinstance(selected_value, int):
            return unsupported_resolution(
                self.resolver_name,
                f"Selected input '{selected_input_name}' did not have a literal value in the test case.",
            )

        return resolved_resolution(
            hardware_spec=hardware_spec,
            resolver_name=self.resolver_name,
            expected_values={output_port.name: selected_value},
            explanation=f"Resolved {output_port.name} from routed input '{selected_input_name}' using explicit select mapping.",
        )


class OneHotDecoderResolver(ReferenceResolver):
    """Resolve one-hot decoder outputs when the mapping is explicit in the HardwareSpec."""

    resolver_name = "one_hot_decoder"

    def can_resolve(self, hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool:
        if hardware_spec.design_type != DesignType.COMBINATIONAL:
            return False

        input_ports = get_ports_by_direction(hardware_spec, "input")
        output_ports = get_ports_by_direction(hardware_spec, "output")
        if len(input_ports) != 1 or len(output_ports) != 1:
            return False

        input_port = input_ports[0]
        output_port = output_ports[0]
        if output_port.width != 1 << input_port.width:
            return False

        rule_text = " ".join(
            [hardware_spec.description or "", *hardware_spec.behavior.rules, *hardware_spec.behavior.operations]
        ).lower()
        if "one-hot" not in rule_text and f"{output_port.name.lower()}[n]" not in rule_text:
            return False

        values = extract_signal_values([*test_case.setup, *test_case.stimulus], {input_port.name})
        return input_port.name in values

    def resolve(
        self,
        hardware_spec: HardwareSpec,
        test_case: VerificationTestCase,
    ) -> ReferenceResolution:
        input_port = get_ports_by_direction(hardware_spec, "input")[0]
        output_port = get_ports_by_direction(hardware_spec, "output")[0]
        values = extract_signal_values([*test_case.setup, *test_case.stimulus], {input_port.name})
        input_value = values.get(input_port.name)

        if not isinstance(input_value, int):
            return unsupported_resolution(self.resolver_name, "Decoder input literal could not be parsed safely.")
        if input_value < 0 or input_value >= (1 << input_port.width):
            return unsupported_resolution(
                self.resolver_name,
                "Decoder input literal was outside the input width range.",
            )

        return resolved_resolution(
            hardware_spec=hardware_spec,
            resolver_name=self.resolver_name,
            expected_values={output_port.name: 1 << input_value},
            explanation="Computed one-hot decoder output directly from the explicit input literal.",
        )


class FixedWidthCounterResolver(ReferenceResolver):
    """Resolve simple fixed-width counter transitions when literals are explicit."""

    resolver_name = "fixed_width_counter_transition"

    def can_resolve(self, hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool:
        if hardware_spec.design_type != DesignType.SEQUENTIAL or hardware_spec.clock is None:
            return False

        output_ports = get_ports_by_direction(hardware_spec, "output")
        if len(output_ports) != 1:
            return False

        spec_text = " ".join(
            [
                hardware_spec.module_name,
                hardware_spec.description or "",
                *hardware_spec.behavior.operations,
                *hardware_spec.behavior.rules,
                *hardware_spec.tags,
            ]
        )
        if not contains_any(spec_text, ["counter", "increment", "decrement", "wrap", "wraparound"]):
            return False

        text = make_test_case_text(test_case)
        return contains_any(text, ["increment", "decrement", "hold", "wrap", "wraparound", "count"])

    def resolve(
        self,
        hardware_spec: HardwareSpec,
        test_case: VerificationTestCase,
    ) -> ReferenceResolution:
        output_port = get_ports_by_direction(hardware_spec, "output")[0]
        state_name = output_port.name
        state_width = output_port.width
        modulus = 1 << state_width

        reset_active = extract_reset_active_state(hardware_spec, test_case)
        reset_value = extract_reset_value(hardware_spec, state_name) or 0
        edge_count = extract_active_edge_count(hardware_spec, make_test_case_text(test_case))
        enable_state = extract_enable_state(hardware_spec, make_test_case_text(test_case))
        start_state = extract_state_precondition(test_case, state_name)

        if reset_active is True:
            if hardware_spec.reset is not None and hardware_spec.reset.type == ResetType.SYNCHRONOUS and edge_count is None:
                return unsupported_resolution(
                    self.resolver_name,
                    "Synchronous reset behavior requires an explicit active clock edge.",
                )
            return resolved_resolution(
                hardware_spec=hardware_spec,
                resolver_name=self.resolver_name,
                expected_values={state_name: reset_value},
                explanation="Resolved state directly from explicit reset semantics in the HardwareSpec.",
            )

        if start_state is None or edge_count is None:
            return unsupported_resolution(
                self.resolver_name,
                "Counter transition needs a known starting state and explicit active-edge count.",
            )

        if enable_state is None:
            enable_state = True

        direction = infer_counter_direction(hardware_spec)
        if enable_state:
            if direction == "down":
                next_state = (start_state - edge_count) % modulus
            else:
                next_state = (start_state + edge_count) % modulus
        else:
            next_state = start_state

        return resolved_resolution(
            hardware_spec=hardware_spec,
            resolver_name=self.resolver_name,
            expected_values={state_name: next_state},
            explanation="Computed fixed-width counter transition from explicit precondition, enable state, and active edges.",
        )


def resolved_resolution(
    hardware_spec: HardwareSpec,
    resolver_name: str,
    expected_values: dict[str, int | str],
    explanation: str,
) -> ReferenceResolution:
    """Build a successful deterministic resolution."""

    return ReferenceResolution(
        status=ReferenceResolutionStatus.RESOLVED,
        resolver=resolver_name,
        expected_values=expected_values,
        canonical_expected=format_expected_values(hardware_spec, expected_values),
        explanation=explanation,
        error_type=None,
        error_message=None,
    )


def unsupported_resolution(resolver_name: str, explanation: str) -> ReferenceResolution:
    """Build a safe unsupported-resolution result."""

    return ReferenceResolution(
        status=ReferenceResolutionStatus.UNSUPPORTED,
        resolver=resolver_name,
        expected_values={},
        canonical_expected=[],
        explanation=explanation,
        error_type=None,
        error_message=None,
    )


def find_port(hardware_spec: HardwareSpec, port_name: str) -> PortView | None:
    """Return one port view if the named port exists."""

    for port in hardware_spec.ports:
        if port.name == port_name:
            return PortView(
                name=port.name,
                width=port.width,
                role=port.role.value,
                direction=port.direction.value,
                signed=port.signed,
            )
    return None


def get_ports_by_direction(hardware_spec: HardwareSpec, direction: str) -> list[PortView]:
    """Return normalized views for ports matching one direction."""

    ports: list[PortView] = []
    for port in hardware_spec.ports:
        if port.direction.value == direction:
            ports.append(
                PortView(
                    name=port.name,
                    width=port.width,
                    role=port.role.value,
                    direction=port.direction.value,
                    signed=port.signed,
                )
            )
    return ports


def find_control_port(hardware_spec: HardwareSpec) -> PortView | None:
    """Return a likely control port for combinational select-routing designs."""

    for port in hardware_spec.ports:
        if port.direction.value != "input":
            continue
        if port.role in {PortRole.CONTROL, PortRole.STATUS}:
            return find_port(hardware_spec, port.name)
    for port in hardware_spec.ports:
        if port.direction.value == "input" and port.name.lower() in {"select", "sel", "s"}:
            return find_port(hardware_spec, port.name)
    return None


def derive_select_mapping(
    hardware_spec: HardwareSpec,
    control_name: str,
    output_name: str,
    data_inputs: list[PortView],
) -> dict[int, str] | None:
    """Derive select-to-input routing from HardwareSpec behavior text."""

    mapping: dict[int, str] = {}
    all_rules = [hardware_spec.description or "", *hardware_spec.behavior.rules]
    for rule in all_rules:
        lowered = rule.lower()
        if control_name.lower() not in lowered or output_name.lower() not in lowered:
            continue
        for data_input in data_inputs:
            if data_input.name.lower() not in lowered:
                continue
            value_match = re.search(rf"{re.escape(control_name)}[^0-9]*([0-9]+)", lowered, re.IGNORECASE)
            if value_match is None:
                continue
            mapping[int(value_match.group(1), 10)] = data_input.name

    return mapping or None


def extract_signal_values(items: list[str], signal_names: set[str] | None = None) -> dict[str, int | str]:
    """Extract simple assignment-style signal literals from text items."""

    values: dict[str, int | str] = {}
    for item in items:
        parsed = parse_signal_assignment(item, signal_names)
        if parsed is None:
            continue
        signal_name, literal_value = parsed
        values[signal_name] = literal_value
    return values


def parse_signal_assignment(text: str, signal_names: set[str] | None = None) -> tuple[str, int | str] | None:
    """Parse a conservative signal=value literal with optional action prefixes."""

    signal_pattern = r"[A-Za-z_][A-Za-z0-9_$]*"
    if signal_names:
        signal_pattern = "|".join(re.escape(name) for name in sorted(signal_names, key=len, reverse=True))

    match = re.search(
        rf"\b(?:drive|set|expect|expected|check|assert|precondition:)?\s*"
        rf"({signal_pattern})\s*=\s*([A-Za-z0-9_'xbodhXBODH]+)\b",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None

    signal_name = match.group(1)
    literal = parse_literal_value(match.group(2))
    if literal is None:
        return None
    return signal_name, literal


def parse_literal_value(token: str) -> int | str | None:
    """Parse plain integers and simple SystemVerilog based literals."""

    stripped = token.strip()
    if not stripped:
        return None
    if stripped.isdigit():
        return int(stripped, 10)

    based_match = re.fullmatch(r"(\d+)'([bBoOdDhH])([0-9a-fA-F_xXzZ]+)", stripped)
    if based_match is None:
        return None

    base = based_match.group(2).lower()
    digits = based_match.group(3).replace("_", "")
    if any(character in digits.lower() for character in ("x", "z")):
        return None

    radix = {"b": 2, "o": 8, "d": 10, "h": 16}[base]
    return int(digits, radix)


def compute_alu_expected_values(
    hardware_spec: HardwareSpec,
    operation: str,
    a_value: int,
    b_value: int,
    width: int,
) -> dict[str, int]:
    """Compute deterministic fixed-width unsigned ALU outputs."""
    return compute_unsigned_alu_outputs(
        hardware_spec=hardware_spec,
        operation=operation,
        a_value=a_value,
        b_value=b_value,
        width=width,
    )


def format_expected_values(hardware_spec: HardwareSpec, expected_values: dict[str, int | str]) -> list[str]:
    """Render deterministic expected values into a stable list-of-strings form."""

    expected_lines: list[str] = []
    emitted_names: set[str] = set()
    for port in hardware_spec.ports:
        if port.direction.value != "output":
            continue
        if port.name not in expected_values:
            continue
        expected_lines.append(f"{port.name}={format_expected_value(expected_values[port.name])}")
        emitted_names.add(port.name)

    for signal_name in sorted(name for name in expected_values if name not in emitted_names):
        expected_lines.append(f"{signal_name}={format_expected_value(expected_values[signal_name])}")

    return expected_lines


def format_expected_value(value: int | str) -> str:
    """Format one deterministic value for the final expected list."""

    if isinstance(value, int):
        return str(value)
    return value


def make_test_case_text(test_case: VerificationTestCase) -> str:
    """Flatten one test case into a searchable lowercased text surface."""

    return "\n".join(
        [
            test_case.id,
            test_case.name,
            test_case.description,
            *test_case.setup,
            *test_case.stimulus,
            *test_case.expected,
            *test_case.covers,
        ]
    ).lower()


def contains_any(text: str, phrases: list[str]) -> bool:
    """Return True when any normalized phrase appears in normalized text."""

    normalized_text = " ".join(text.lower().split())
    return any(" ".join(phrase.lower().split()) in normalized_text for phrase in phrases)


def extract_reset_active_state(hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool | None:
    """Return whether reset is explicitly active or inactive in the test case."""

    if hardware_spec.reset is None:
        return None

    reset_signal = hardware_spec.reset.signal
    signal_values = extract_signal_values([*test_case.setup, *test_case.stimulus], {reset_signal})
    reset_value = signal_values.get(reset_signal)
    if not isinstance(reset_value, int):
        return None

    if hardware_spec.reset.polarity.value == "active_high":
        return reset_value == 1
    return reset_value == 0


def extract_reset_value(hardware_spec: HardwareSpec, state_name: str) -> int | None:
    """Return one reset value when it is explicitly numeric in the HardwareSpec."""

    if hardware_spec.reset is None:
        return None
    raw_value = hardware_spec.reset.reset_values.get(state_name)
    if isinstance(raw_value, int):
        return raw_value
    return None


def extract_state_precondition(test_case: VerificationTestCase, state_name: str) -> int | None:
    """Extract a conceptual starting state without treating it as a drive command."""

    search_fields = [" ".join(test_case.setup), test_case.description]
    patterns = [
        rf"\bstarting\s+{re.escape(state_name)}\s*=\s*(\d+)\b",
        rf"\bstart\s+{re.escape(state_name)}\s*=\s*(\d+)\b",
        rf"\b{re.escape(state_name)}\s+has\s+reached\s+(\d+)\b",
        rf"\bbring\s+{re.escape(state_name)}\s+to\s+(\d+)\b",
        rf"\breach\s+{re.escape(state_name)}\s*=\s*(\d+)\b",
        rf"\bprecondition:\s*{re.escape(state_name)}\s*(?:is|=)\s*(\d+)\b",
        rf"\b{re.escape(state_name)}\s+is\s+currently\s+at\s+(\d+)\b",
        rf"\bat\s+{re.escape(state_name)}\s*=\s*(\d+)\b",
    ]

    for field in search_fields:
        for pattern in patterns:
            match = re.search(pattern, field, re.IGNORECASE)
            if match is not None:
                return int(match.group(1), 10)
    return None


def extract_active_edge_count(hardware_spec: HardwareSpec, text: str) -> int | None:
    """Extract the number of active clock events referenced in one test."""

    if hardware_spec.clock is None:
        return None

    if hardware_spec.clock.edge.value == "positive":
        edge_pattern = r"(?:rising|positive|active)\s+edge|0->1\s+transition"
    else:
        edge_pattern = r"(?:falling|negative|active)\s+edge|1->0\s+transition"

    patterns = [
        rf"\b(\d+)\s+{edge_pattern}s?\b",
        rf"\bone\s+{edge_pattern}\b",
        rf"\bnext\s+{edge_pattern}\b",
        rf"\ban?\s+additional\s+{edge_pattern}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        if match.lastindex and match.group(1):
            return int(match.group(1), 10)
        return 1
    return None


def extract_enable_state(hardware_spec: HardwareSpec, text: str) -> bool | None:
    """Extract whether an enable-style input is explicitly asserted or deasserted."""

    enable_ports = [
        port.name
        for port in hardware_spec.ports
        if port.direction.value == "input" and port.name.lower() in {"en", "enable"}
    ]
    if not enable_ports:
        return True

    pattern = "|".join(re.escape(name) for name in enable_ports)
    if re.search(rf"\b(?:{pattern})\s*=\s*1\b", text, re.IGNORECASE) or contains_any(text, ["enable high", "enabled"]):
        return True
    if re.search(rf"\b(?:{pattern})\s*=\s*0\b", text, re.IGNORECASE) or contains_any(text, ["enable low", "disabled"]):
        return False
    return None


def infer_counter_direction(hardware_spec: HardwareSpec) -> str:
    """Infer a simple counter direction conservatively from structured behavior text."""

    text = " ".join(
        [
            hardware_spec.description or "",
            *hardware_spec.behavior.rules,
            *hardware_spec.behavior.operations,
            *hardware_spec.tags,
        ]
    ).lower()
    if "down" in text and "up" not in text and "increment" not in text:
        return "down"
    return "up"
