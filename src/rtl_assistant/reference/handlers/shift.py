import re

from rtl_assistant.models.hardware_spec import HardwareSpec


def infer_shift_direction(hardware_spec: HardwareSpec) -> str | None:
    """Infer a simple shift direction from structured HardwareSpec semantics."""

    text = " ".join(
        [
            hardware_spec.description or "",
            hardware_spec.behavior.description,
            *hardware_spec.behavior.operations,
            *hardware_spec.behavior.rules,
            *hardware_spec.tags,
        ]
    ).lower()

    if contains_any(text, ["shift left", "left shift", "shift_left"]):
        return "left"
    if contains_any(text, ["shift right", "right shift", "shift_right"]):
        return "right"
    return None


def infer_serial_input_signal(hardware_spec: HardwareSpec) -> str | None:
    """Return a likely serial-input signal name when one is clearly present."""

    for port in hardware_spec.ports:
        if port.direction.value != "input":
            continue
        if port.name.lower() in {"serial_in", "din", "sin"}:
            return port.name
    for port in hardware_spec.ports:
        if port.direction.value == "input" and "serial" in port.name.lower():
            return port.name
    return None


def infer_shift_state_output(hardware_spec: HardwareSpec) -> str | None:
    """Return a likely observable state/output signal for a shift register."""

    output_ports = [port.name for port in hardware_spec.ports if port.direction.value == "output"]
    if len(output_ports) == 1:
        return output_ports[0]
    return None


def compute_shift_next_state(
    current_state: int,
    serial_in: int,
    width: int,
    direction: str,
) -> int:
    """Compute one fixed-width next state for a simple serial shift register."""

    mask = (1 << width) - 1
    if direction == "left":
        return ((current_state << 1) & mask) | (serial_in & 0x1)
    if direction == "right":
        return ((current_state >> 1) & mask) | ((serial_in & 0x1) << (width - 1))
    raise ValueError(f"Unsupported shift direction: {direction}")


def behavior_mentions_shift_semantics(hardware_spec: HardwareSpec) -> bool:
    """Return True when the HardwareSpec clearly describes shift-register behavior."""

    text = " ".join(
        [
            hardware_spec.description or "",
            hardware_spec.behavior.description,
            *hardware_spec.behavior.operations,
            *hardware_spec.behavior.rules,
            *hardware_spec.tags,
        ]
    ).lower()
    return infer_shift_direction(hardware_spec) is not None and contains_any(text, ["serial", "shift"])


def contains_any(text: str, phrases: list[str]) -> bool:
    """Return True when any normalized phrase appears in normalized text."""

    normalized = " ".join(text.lower().replace("_", " ").split())
    return any(" ".join(phrase.lower().replace("_", " ").split()) in normalized for phrase in phrases)


def contains_shift_hold_language(text: str) -> bool:
    """Return True when test text appears to describe hold behavior."""

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in (
            r"\bhold(?:s|ing)?\b",
            r"\bremains?\b",
            r"\bunchanged\b",
            r"\bprevious value\b",
        )
    )
