import re
from collections import OrderedDict

from rtl_assistant.models.hardware_spec import HardwareSpec, PortRole
from rtl_assistant.models.verification_plan import VerificationPlan, VerificationTestCase
from rtl_assistant.reference.handlers.alu import parse_numeric_literal
from rtl_assistant.testbench.ir import (
    ExpectedCheck,
    InputAssignment,
    TestbenchAction,
    TestbenchActionType,
    TestbenchCase,
    TestbenchPlan,
)


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
}


class TestbenchTranslationError(Exception):
    """Structured deterministic-translation failure."""

    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(f"{error_type}: {message}")
        self.error_type = error_type
        self.message = message


def translate_verification_plan(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
) -> TestbenchPlan:
    """Translate a validated VerificationPlan into a deterministic executable IR."""

    translated_cases = [
        translate_test_case(hardware_spec, test_case)
        for test_case in verification_plan.test_cases
    ]
    return TestbenchPlan(
        module_name=hardware_spec.module_name,
        design_type=hardware_spec.design_type,
        tests=translated_cases,
    )


def translate_test_case(
    hardware_spec: HardwareSpec,
    test_case: VerificationTestCase,
) -> TestbenchCase:
    """Translate one verification-plan test into deterministic actions and checks."""

    checks = parse_expected_checks(hardware_spec, test_case)
    if hardware_spec.design_type.value == "combinational":
        actions = translate_combinational_actions(hardware_spec, test_case)
    else:
        actions = translate_sequential_actions(hardware_spec, test_case)

    return TestbenchCase(
        id=test_case.id,
        name=test_case.name,
        actions=actions,
        checks=checks,
    )


def parse_expected_checks(
    hardware_spec: HardwareSpec,
    test_case: VerificationTestCase,
) -> list[ExpectedCheck]:
    """Parse explicit expected output checks from a test case."""

    output_names = {
        port.name: port
        for port in hardware_spec.ports
        if port.direction.value == "output"
    }
    checks: list[ExpectedCheck] = []

    for item in test_case.expected:
        expected_check = parse_expected_check(hardware_spec, item)
        if expected_check is None:
            raise TestbenchTranslationError(
                "MISSING_EXPECTED_VALUE",
                f"Test '{test_case.id}' contains unsupported expected text: {item}",
            )

        signal_name = expected_check.signal
        if signal_name not in output_names:
            raise TestbenchTranslationError(
                "UNKNOWN_SIGNAL",
                f"Test '{test_case.id}' expects unknown or non-output signal '{signal_name}'.",
            )

        if expected_check.value is not None:
            validate_value_fits_width(
                signal_name=signal_name,
                value=expected_check.value,
                width=output_names[signal_name].width,
                error_type="MISSING_EXPECTED_VALUE",
                context=f"Test '{test_case.id}' expected value for '{signal_name}'",
            )
        elif expected_check.reference_signal is not None:
            reference_port = find_port(hardware_spec, expected_check.reference_signal)
            if reference_port is None:
                raise TestbenchTranslationError(
                    "UNKNOWN_SIGNAL",
                    f"Test '{test_case.id}' expects unknown reference signal '{expected_check.reference_signal}'.",
                )
            if reference_port.width != output_names[signal_name].width:
                raise TestbenchTranslationError(
                    "MISSING_EXPECTED_VALUE",
                    f"Test '{test_case.id}' compares '{signal_name}' to '{expected_check.reference_signal}' with mismatched widths.",
                )

        checks.append(expected_check)

    if not checks:
        raise TestbenchTranslationError(
            "MISSING_EXPECTED_VALUE",
            f"Test '{test_case.id}' does not contain any parseable expected output values.",
        )

    return checks


def translate_combinational_actions(
    hardware_spec: HardwareSpec,
    test_case: VerificationTestCase,
) -> list[TestbenchAction]:
    """Translate one combinational test into input assignments plus one settle step."""

    input_ports = {port.name: port for port in hardware_spec.ports if port.direction.value == "input"}
    ordered_assignments: OrderedDict[str, int] = OrderedDict()

    for item in [*test_case.setup, *test_case.stimulus]:
        parsed = parse_named_assignment(hardware_spec, item)
        if parsed is None:
            raise TestbenchTranslationError(
                "UNSUPPORTED_TESTBENCH_ACTION",
                f"Test '{test_case.id}' contains unsupported combinational action text: {item}",
            )

        signal_name, value = parsed
        if signal_name not in input_ports:
            error_type = "OUTPUT_USED_AS_STIMULUS" if is_output_signal(hardware_spec, signal_name) else "UNKNOWN_SIGNAL"
            raise TestbenchTranslationError(
                error_type,
                f"Test '{test_case.id}' tries to drive invalid combinational signal '{signal_name}'.",
            )
        validate_value_fits_width(
            signal_name=signal_name,
            value=value,
            width=input_ports[signal_name].width,
            error_type="INVALID_INPUT_ASSIGNMENT",
            context=f"Test '{test_case.id}' stimulus value for '{signal_name}'",
        )

        ordered_assignments[signal_name] = value

    if not ordered_assignments:
        raise TestbenchTranslationError(
            "INVALID_INPUT_ASSIGNMENT",
            f"Test '{test_case.id}' does not contain any parseable combinational input assignments.",
        )

    actions = [
        TestbenchAction(
            type=TestbenchActionType.SET_INPUT,
            assignment=InputAssignment(signal=signal_name, value=value),
        )
        for signal_name, value in ordered_assignments.items()
    ]
    actions.append(TestbenchAction(type=TestbenchActionType.SETTLE))
    return actions


def translate_sequential_actions(
    hardware_spec: HardwareSpec,
    test_case: VerificationTestCase,
) -> list[TestbenchAction]:
    """Translate one sequential test into deterministic set/edge/settle actions."""

    actions: list[TestbenchAction] = []
    for item in [*test_case.setup, *test_case.stimulus]:
        translated_actions = translate_sequential_item(hardware_spec, test_case.id, item)
        if not translated_actions:
            raise TestbenchTranslationError(
                "UNSUPPORTED_TESTBENCH_ACTION",
                f"Test '{test_case.id}' contains unsupported sequential action text: {item}",
            )
        actions.extend(translated_actions)

    if not actions:
        raise TestbenchTranslationError(
            "UNSUPPORTED_TESTBENCH_ACTION",
            f"Test '{test_case.id}' does not contain any executable sequential actions.",
        )

    if needs_terminal_settle(hardware_spec, actions):
        actions.append(TestbenchAction(type=TestbenchActionType.SETTLE))

    return actions


def translate_sequential_item(
    hardware_spec: HardwareSpec,
    test_id: str,
    item: str,
) -> list[TestbenchAction]:
    """Translate one sequential action line conservatively."""

    parsed_assignment = parse_named_assignment(hardware_spec, item)
    if parsed_assignment is not None:
        signal_name, value = parsed_assignment
        validate_input_signal(hardware_spec, test_id, signal_name)
        input_width = find_port_width(hardware_spec, signal_name)
        if input_width is None:
            raise TestbenchTranslationError(
                "UNKNOWN_SIGNAL",
                f"Test '{test_id}' references unknown signal '{signal_name}'.",
            )
        validate_value_fits_width(
            signal_name=signal_name,
            value=value,
            width=input_width,
            error_type="INVALID_INPUT_ASSIGNMENT",
            context=f"Test '{test_id}' stimulus value for '{signal_name}'",
        )
        return [
            TestbenchAction(
                type=TestbenchActionType.SET_INPUT,
                assignment=InputAssignment(signal=signal_name, value=value),
            )
        ]

    reset_actions = parse_reset_phrase(hardware_spec, item)
    if reset_actions:
        return reset_actions

    enable_actions = parse_enable_phrase(hardware_spec, item)
    if enable_actions:
        return enable_actions

    edge_actions = parse_edge_phrase(hardware_spec, item)
    if edge_actions:
        return edge_actions

    precondition_actions = parse_precondition_translation(hardware_spec, item)
    if precondition_actions:
        return precondition_actions

    if "settle" in item.lower():
        return [TestbenchAction(type=TestbenchActionType.SETTLE)]

    return []


def parse_reset_phrase(hardware_spec: HardwareSpec, item: str) -> list[TestbenchAction]:
    """Translate explicit reset assert/deassert phrases when reset metadata exists."""

    if hardware_spec.reset is None:
        return []

    lower_item = item.lower()
    reset_signal = hardware_spec.reset.signal
    active_value = 1 if hardware_spec.reset.polarity.value == "active_high" else 0
    inactive_value = 0 if active_value == 1 else 1

    if re.search(rf"\bassert\s+{re.escape(reset_signal.lower())}\b", lower_item) or "assert reset" in lower_item:
        return [make_set_input_action(reset_signal, active_value)]
    if re.search(rf"\bdeassert\s+{re.escape(reset_signal.lower())}\b", lower_item) or "deassert reset" in lower_item:
        return [make_set_input_action(reset_signal, inactive_value)]
    return []


def parse_enable_phrase(hardware_spec: HardwareSpec, item: str) -> list[TestbenchAction]:
    """Translate a few safe enable/disable phrases when an enable input exists."""

    enable_signal = find_enable_signal(hardware_spec)
    if enable_signal is None:
        return []

    lower_item = item.lower()
    if any(phrase in lower_item for phrase in ("enable high", "enable counting", "enabled")):
        return [make_set_input_action(enable_signal, 1)]
    if any(phrase in lower_item for phrase in ("enable low", "disable enable", "disabled")):
        return [make_set_input_action(enable_signal, 0)]
    return []


def parse_edge_phrase(hardware_spec: HardwareSpec, item: str) -> list[TestbenchAction]:
    """Translate explicit active-edge actions."""

    if hardware_spec.clock is None:
        return []

    lower_item = item.lower()
    if "edge" not in lower_item and "posedge" not in lower_item and "negedge" not in lower_item and "transition" not in lower_item:
        return []

    mentioned_edge = infer_edge_from_text(lower_item, hardware_spec)
    if mentioned_edge is None:
        return []
    if mentioned_edge != hardware_spec.clock.edge.value:
        raise TestbenchTranslationError(
            "INVALID_CLOCK_ACTION",
            f"Action '{item}' does not match the HardwareSpec active clock edge.",
        )

    edge_count = parse_edge_count(lower_item)
    if edge_count is None:
        raise TestbenchTranslationError(
            "INVALID_CLOCK_ACTION",
            f"Action '{item}' mentions a clock event but not in a safely translatable way.",
        )

    if edge_count == 1:
        return [TestbenchAction(type=TestbenchActionType.ACTIVE_CLOCK_EDGE)]
    return [TestbenchAction(type=TestbenchActionType.REPEAT_ACTIVE_EDGES, count=edge_count)]


def parse_precondition_translation(hardware_spec: HardwareSpec, item: str) -> list[TestbenchAction]:
    """Translate a narrow set of legal preconditions into executable state-preparation steps."""

    lower_item = item.lower()
    if "precondition:" not in lower_item and " using " not in lower_item and " after " not in lower_item:
        return []

    edge_actions = parse_edge_phrase(hardware_spec, item)
    if not edge_actions:
        return []

    actions: list[TestbenchAction] = []
    if "enabled" in lower_item:
        enable_signal = find_enable_signal(hardware_spec)
        if enable_signal is not None:
            actions.append(make_set_input_action(enable_signal, 1))
    actions.extend(edge_actions)
    return actions


def needs_terminal_settle(
    hardware_spec: HardwareSpec,
    actions: list[TestbenchAction],
) -> bool:
    """Return True when a sequential test should settle once more before checks."""

    del hardware_spec
    if not actions:
        return False
    if actions[-1].type in {TestbenchActionType.ACTIVE_CLOCK_EDGE, TestbenchActionType.REPEAT_ACTIVE_EDGES, TestbenchActionType.SETTLE}:
        return False
    return True


def validate_input_signal(hardware_spec: HardwareSpec, test_id: str, signal_name: str) -> None:
    """Raise structured errors for invalid or unsafe stimulus signals."""

    for port in hardware_spec.ports:
        if port.name != signal_name:
            continue
        if port.direction.value != "input":
            raise TestbenchTranslationError(
                "OUTPUT_USED_AS_STIMULUS",
                f"Test '{test_id}' tries to drive output signal '{signal_name}'.",
            )
        return

    raise TestbenchTranslationError(
        "UNKNOWN_SIGNAL",
        f"Test '{test_id}' references unknown signal '{signal_name}'.",
    )


def is_output_signal(hardware_spec: HardwareSpec, signal_name: str) -> bool:
    """Return True when a named signal is a DUT output."""

    return any(port.name == signal_name and port.direction.value == "output" for port in hardware_spec.ports)


def find_enable_signal(hardware_spec: HardwareSpec) -> str | None:
    """Return the first simple enable-like input signal when present."""

    for port in hardware_spec.ports:
        if port.direction.value == "input" and port.name.lower() in {"en", "enable"}:
            return port.name
    return None


def parse_named_assignment(
    hardware_spec: HardwareSpec,
    item: str,
) -> tuple[str, int] | None:
    """Parse one explicit signal=value assignment using signal/spec-aware literal semantics."""

    match = re.search(
        r"\b(?:drive|set|expect|expected|check|assert|precondition:)?\s*"
        r"([A-Za-z_][A-Za-z0-9_$]*)\s*=\s*([A-Za-z0-9_'xbodhXBODH]+)\b",
        item,
        re.IGNORECASE,
    )
    if match is None:
        return None

    signal_name = match.group(1)
    literal_value = parse_signal_aware_literal(
        hardware_spec=hardware_spec,
        signal_name=signal_name,
        token=match.group(2),
    )
    if literal_value is None:
        return None
    return signal_name, literal_value


def parse_expected_check(
    hardware_spec: HardwareSpec,
    item: str,
) -> ExpectedCheck | None:
    """Parse one expected check as either a literal value or signal equality."""

    symbolic_match = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_$]*)\s*(?:equals|=)\s*([A-Za-z_][A-Za-z0-9_$]*)\b",
        item,
        re.IGNORECASE,
    )
    if symbolic_match is not None:
        actual_signal = symbolic_match.group(1)
        reference_signal = symbolic_match.group(2)
        if actual_signal != reference_signal:
            actual_port = find_port(hardware_spec, actual_signal)
            reference_port = find_port(hardware_spec, reference_signal)
            if actual_port is not None and reference_port is not None:
                return ExpectedCheck(signal=actual_signal, reference_signal=reference_signal)

    parsed_assignment = parse_named_assignment(hardware_spec, item)
    if parsed_assignment is None:
        return None

    signal_name, value = parsed_assignment
    return ExpectedCheck(signal=signal_name, value=value)


def parse_signal_aware_literal(
    hardware_spec: HardwareSpec,
    signal_name: str,
    token: str,
) -> int | None:
    """Parse one literal with signal semantics derived from HardwareSpec when available."""

    stripped = token.strip()
    if not stripped:
        return None

    explicit_value = parse_explicit_numeric_literal(stripped)
    if explicit_value is not None:
        return explicit_value

    mapped_value = parse_mapped_control_token(hardware_spec, signal_name, stripped)
    if mapped_value is not None:
        return mapped_value

    vector_value = parse_width_matched_bit_vector(hardware_spec, signal_name, stripped)
    if vector_value is not None:
        return vector_value

    if stripped.isdigit():
        return int(stripped, 10)

    return None


def parse_explicit_numeric_literal(token: str) -> int | None:
    """Parse an explicitly radixed literal without applying signal semantics."""

    stripped = token.strip()
    if not stripped:
        return None

    binary_prefix_match = re.fullmatch(r"0[bB]([01_]+)", stripped)
    if binary_prefix_match is not None:
        return int(binary_prefix_match.group(1).replace("_", ""), 2)

    return parse_numeric_literal(stripped) if "'" in stripped else None


def parse_mapped_control_token(
    hardware_spec: HardwareSpec,
    signal_name: str,
    token: str,
) -> int | None:
    """Parse a bare token through explicit HardwareSpec control mappings when available."""

    port = find_port(hardware_spec, signal_name)
    if port is None or port.role != PortRole.CONTROL:
        return None

    if not re.fullmatch(r"[01]+", token):
        return None

    mapped_tokens = extract_control_mapping_tokens(hardware_spec, signal_name)
    if not mapped_tokens:
        return None

    normalized_token = token.zfill(port.width)
    if normalized_token not in mapped_tokens:
        return None

    return int(normalized_token, 2)


def parse_width_matched_bit_vector(
    hardware_spec: HardwareSpec,
    signal_name: str,
    token: str,
) -> int | None:
    """Parse a bare width-matched binary token when signal semantics make that safe."""

    port = find_port(hardware_spec, signal_name)
    if port is None or not re.fullmatch(r"[01]+", token):
        return None

    if len(token) != port.width:
        return None

    if port.role == PortRole.CONTROL:
        return int(token, 2)

    if port.direction.value == "output":
        return int(token, 2)

    return None


def extract_control_mapping_tokens(hardware_spec: HardwareSpec, signal_name: str) -> set[str]:
    """Extract explicit encoded control tokens for one control signal from HardwareSpec rules."""

    port = find_port(hardware_spec, signal_name)
    if port is None or port.role != PortRole.CONTROL:
        return set()

    tokens: set[str] = set()
    signal_pattern = re.escape(signal_name)
    for rule in hardware_spec.behavior.rules:
        match = re.search(
            rf"\b{signal_pattern}\b\s+([A-Za-z0-9_'xbodhXBODH]+)\b",
            rule,
            re.IGNORECASE,
        )
        if match is None:
            continue
        normalized_token = normalize_control_mapping_token(match.group(1), port.width)
        if normalized_token is not None:
            tokens.add(normalized_token)
    return tokens


def validate_value_fits_width(
    signal_name: str,
    value: int,
    width: int,
    error_type: str,
    context: str,
) -> None:
    """Reject values that cannot be represented by the destination signal width."""

    if width < 1:
        raise TestbenchTranslationError(
            error_type,
            f"{context} targets invalid width {width} for signal '{signal_name}'.",
        )
    if value < 0:
        raise TestbenchTranslationError(
            error_type,
            f"{context} uses unsupported negative value {value} for signal '{signal_name}'.",
        )

    max_value = (1 << width) - 1
    if value > max_value:
        raise TestbenchTranslationError(
            error_type,
            f"{context} value {value} does not fit in {width} bits for signal '{signal_name}'.",
        )


def find_port(
    hardware_spec: HardwareSpec,
    signal_name: str,
):
    """Return the matching HardwareSpec port when present."""

    for port in hardware_spec.ports:
        if port.name == signal_name:
            return port
    return None


def find_port_width(hardware_spec: HardwareSpec, signal_name: str) -> int | None:
    """Return the declared width of one named HardwareSpec port."""

    port = find_port(hardware_spec, signal_name)
    return None if port is None else port.width


def normalize_control_mapping_token(token: str, width: int) -> str | None:
    """Normalize one explicit HardwareSpec control token into a stable binary encoding."""

    stripped = token.strip()
    if not stripped:
        return None

    if re.fullmatch(r"[01]+", stripped):
        return stripped.zfill(width)

    explicit_value = parse_explicit_numeric_literal(stripped)
    if explicit_value is not None:
        if explicit_value < 0 or explicit_value > (1 << width) - 1:
            return None
        return format(explicit_value, f"0{width}b")

    if stripped.isdigit():
        numeric_value = int(stripped, 10)
        if numeric_value > (1 << width) - 1:
            return None
        return format(numeric_value, f"0{width}b")

    return None


def make_set_input_action(signal_name: str, value: int) -> TestbenchAction:
    """Build one SET_INPUT action."""

    return TestbenchAction(
        type=TestbenchActionType.SET_INPUT,
        assignment=InputAssignment(signal=signal_name, value=value),
    )


def infer_edge_from_text(text: str, hardware_spec: HardwareSpec) -> str | None:
    """Infer the referenced edge kind from text."""

    if any(token in text for token in ("posedge", "rising edge", "positive edge", "0->1 transition")):
        return "positive"
    if any(token in text for token in ("negedge", "falling edge", "negative edge", "1->0 transition")):
        return "negative"
    if "active edge" in text:
        return hardware_spec.clock.edge.value if hardware_spec.clock is not None else None
    return None


def parse_edge_count(text: str) -> int | None:
    """Parse one explicit active-edge repetition count."""

    digit_match = re.search(
        r"\b(\d+)\s+(?:enabled\s+)?(?:rising|positive|falling|negative|active)\s+edges?\b",
        text,
    )
    if digit_match is not None:
        return int(digit_match.group(1), 10)

    word_match = re.search(
        r"\b(" + "|".join(NUMBER_WORDS) + r")\s+(?:enabled\s+)?(?:rising|positive|falling|negative|active)\s+edges?\b",
        text,
    )
    if word_match is not None:
        return NUMBER_WORDS[word_match.group(1)]

    if any(phrase in text for phrase in ("one rising edge", "one falling edge", "one active edge", "next active edge", "one additional rising edge", "one additional falling edge", "one additional active edge")):
        return 1

    if any(phrase in text for phrase in ("posedge", "negedge", "rising edge", "falling edge", "positive edge", "negative edge", "active edge", "0->1 transition", "1->0 transition")):
        return 1

    return None
