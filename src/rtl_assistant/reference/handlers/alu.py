import re
from dataclasses import dataclass

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.verification_plan import VerificationTestCase


SUPPORTED_ALU_OPERATIONS = ("ADD", "SUB", "AND", "OR")


@dataclass(slots=True)
class ALULiteralVector:
    """Explicit ALU literals parsed conservatively from one test case."""

    a: int | None = None
    b: int | None = None
    opcode_token: str | None = None
    expected_result: int | None = None
    expected_carry: int | None = None
    expected_zero: int | None = None


def extract_alu_literal_vector(
    hardware_spec: HardwareSpec,
    test_case: VerificationTestCase,
) -> ALULiteralVector:
    """Extract conservative explicit ALU literals from one test case."""

    return extract_alu_literal_vector_from_items(
        hardware_spec=hardware_spec,
        items=[*test_case.setup, *test_case.stimulus, *test_case.expected],
    )


def extract_alu_stimulus_vector(
    hardware_spec: HardwareSpec,
    test_case: VerificationTestCase,
) -> ALULiteralVector:
    """Extract ALU literals only from setup and stimulus text."""

    return extract_alu_literal_vector_from_items(
        hardware_spec=hardware_spec,
        items=[*test_case.setup, *test_case.stimulus],
    )


def extract_alu_literal_vector_from_items(
    hardware_spec: HardwareSpec,
    items: list[str],
) -> ALULiteralVector:
    """Extract conservative explicit ALU literals from a chosen set of plan strings."""

    opcode_width = find_port_width(hardware_spec, "opcode")
    vector = ALULiteralVector()

    for item in items:
        parsed = parse_alu_assignment(item, opcode_width)
        if parsed is None:
            continue
        signal_name, literal_value = parsed
        if signal_name == "a" and isinstance(literal_value, int):
            vector.a = literal_value
        elif signal_name == "b" and isinstance(literal_value, int):
            vector.b = literal_value
        elif signal_name == "opcode" and isinstance(literal_value, str):
            vector.opcode_token = literal_value
        elif signal_name == "result" and isinstance(literal_value, int):
            vector.expected_result = literal_value
        elif signal_name == "carry" and isinstance(literal_value, int):
            vector.expected_carry = literal_value
        elif signal_name == "zero" and isinstance(literal_value, int):
            vector.expected_zero = literal_value

    return vector


def extract_alu_opcode_mapping(hardware_spec: HardwareSpec) -> dict[str, str]:
    """Extract explicit opcode-to-operation mapping from structured HardwareSpec rules only."""

    opcode_width = find_port_width(hardware_spec, "opcode")
    mapping: dict[str, str] = {}

    if opcode_width is None:
        return mapping

    for rule in hardware_spec.behavior.rules:
        match = re.search(
            r"opcode\s+([01]+|\d+)\s+(?:performs|is)\s+([A-Za-z_][A-Za-z0-9_]*)",
            rule,
            re.IGNORECASE,
        )
        if match is None:
            continue

        opcode_token = normalize_opcode_token(match.group(1), opcode_width)
        operation = match.group(2).upper()
        if opcode_token is None or operation not in SUPPORTED_ALU_OPERATIONS:
            continue
        mapping[opcode_token] = operation

    return mapping


def resolve_alu_operation_from_vector(
    hardware_spec: HardwareSpec,
    vector: ALULiteralVector,
) -> str | None:
    """Resolve the ALU operation only when opcode mapping is explicit and unambiguous."""

    if vector.opcode_token is None:
        return None

    opcode_mapping = extract_alu_opcode_mapping(hardware_spec)
    if not opcode_mapping:
        return None

    return opcode_mapping.get(vector.opcode_token)


def compute_unsigned_alu_outputs(
    hardware_spec: HardwareSpec,
    operation: str,
    a_value: int,
    b_value: int,
    width: int,
) -> dict[str, int]:
    """Compute fixed-width unsigned ALU outputs from one shared deterministic implementation."""

    if width < 1 or operation not in SUPPORTED_ALU_OPERATIONS:
        return {}

    result_value: int
    carry_value: int | None = None

    if operation == "ADD":
        result_value, carry_value = resolve_alu_add(a_value, b_value, width)
    elif operation == "SUB":
        result_value = resolve_alu_sub(a_value, b_value, width)
        carry_value = derive_non_add_carry_value(hardware_spec, operation)
    elif operation == "AND":
        result_value = resolve_alu_and(a_value, b_value, width)
    else:
        result_value = resolve_alu_or(a_value, b_value, width)

    expected_values: dict[str, int] = {"result": result_value}
    if carry_value is not None and find_port_width(hardware_spec, "carry") is not None:
        expected_values["carry"] = carry_value
    if find_port_width(hardware_spec, "zero") is not None:
        expected_values["zero"] = 1 if result_value == 0 else 0
    return expected_values


def resolve_alu_add(a_value: int, b_value: int, width: int) -> tuple[int, int]:
    """Resolve one fixed-width unsigned ADD result and carry."""

    mask = (1 << width) - 1
    full_value = a_value + b_value
    return full_value & mask, 1 if full_value > mask else 0


def resolve_alu_sub(a_value: int, b_value: int, width: int) -> int:
    """Resolve one fixed-width unsigned SUB result."""

    mask = (1 << width) - 1
    return (a_value - b_value) & mask


def resolve_alu_and(a_value: int, b_value: int, width: int) -> int:
    """Resolve one fixed-width unsigned AND result."""

    mask = (1 << width) - 1
    return (a_value & b_value) & mask


def resolve_alu_or(a_value: int, b_value: int, width: int) -> int:
    """Resolve one fixed-width unsigned OR result."""

    mask = (1 << width) - 1
    return (a_value | b_value) & mask


def derive_non_add_carry_value(hardware_spec: HardwareSpec, operation: str) -> int | None:
    """Derive non-ADD carry semantics only when HardwareSpec states them explicitly."""

    for rule in hardware_spec.behavior.rules:
        upper_rule = rule.upper()
        if operation not in upper_rule or "CARRY" not in upper_rule:
            continue
        if re.search(r"carry(?:\s+\w+)*\s+0\b|carry\s*=\s*0\b", rule, re.IGNORECASE):
            return 0
        if re.search(r"carry(?:\s+\w+)*\s+1\b|carry\s*=\s*1\b", rule, re.IGNORECASE):
            return 1
    return None


def parse_alu_assignment(text: str, opcode_width: int | None) -> tuple[str, int | str] | None:
    """Parse one conservative ALU assignment from plan text."""

    match = re.search(
        r"\b(?:drive|set|expect|expected|check|assert)?\s*"
        r"(a|b|opcode|result|carry|zero)\s*=\s*([A-Za-z0-9_'xbodhXBODH]+)\b",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None

    signal_name = match.group(1).lower()
    token = match.group(2)
    if signal_name == "opcode":
        opcode_token = normalize_opcode_token(token, opcode_width)
        if opcode_token is None:
            return None
        return signal_name, opcode_token

    literal_value = parse_numeric_literal(token)
    if literal_value is None:
        return None
    return signal_name, literal_value


def parse_numeric_literal(token: str) -> int | None:
    """Parse plain decimal or simple SystemVerilog numeric literal text."""

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


def normalize_opcode_token(value: str | int, opcode_width: int | None) -> str | None:
    """Normalize opcode literals into one stable zero-padded binary token."""

    if opcode_width is None:
        return None

    if isinstance(value, int):
        if value < 0:
            return None
        return format(value, f"0{opcode_width}b")

    stripped = value.strip()
    if not stripped:
        return None

    if re.fullmatch(r"[01]+", stripped):
        return stripped.zfill(opcode_width)
    if stripped.isdigit():
        return format(int(stripped, 10), f"0{opcode_width}b")

    numeric_value = parse_numeric_literal(stripped)
    if numeric_value is None:
        return None
    return format(numeric_value, f"0{opcode_width}b")


def find_port_width(hardware_spec: HardwareSpec, port_name: str) -> int | None:
    """Return the width of one named port when present."""

    for port in hardware_spec.ports:
        if port.name == port_name:
            return port.width
    return None
