import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from pydantic import ValidationError

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.reference.handlers.alu import compute_unsigned_alu_outputs


def parse_arguments() -> argparse.Namespace:
    """Parse arguments for deterministic ALU reference checking."""

    parser = argparse.ArgumentParser(
        description="Run the shared deterministic ALU reference logic without invoking any LLM."
    )
    parser.add_argument("spec_path", help="Path to the validated HardwareSpec JSON file.")
    parser.add_argument("--op", required=True, choices=["ADD", "SUB", "AND", "OR"], help="ALU operation.")
    parser.add_argument("--a", required=True, type=int, help="Operand A as an unsigned integer.")
    parser.add_argument("--b", required=True, type=int, help="Operand B as an unsigned integer.")
    parser.add_argument("--expect-result", type=int, help="Optional expected result value.")
    parser.add_argument("--expect-carry", type=int, choices=[0, 1], help="Optional expected carry value.")
    parser.add_argument("--expect-zero", type=int, choices=[0, 1], help="Optional expected zero value.")
    return parser.parse_args()


def load_hardware_spec(spec_path_str: str) -> HardwareSpec:
    """Read and validate a HardwareSpec JSON file."""

    spec_path = Path(spec_path_str)
    if not spec_path.exists() or not spec_path.is_file():
        raise FileNotFoundError(f"HardwareSpec file not found or is not a file: {spec_path}")

    raw_json = spec_path.read_text(encoding="utf-8")
    json.loads(raw_json)
    return HardwareSpec.model_validate_json(raw_json)


def find_result_width(hardware_spec: HardwareSpec) -> int:
    """Return the ALU result width from the validated HardwareSpec."""

    for port in hardware_spec.ports:
        if port.name == "result":
            return port.width
    raise ValueError("HardwareSpec does not define a 'result' output port.")


def main() -> int:
    args = parse_arguments()

    try:
        hardware_spec = load_hardware_spec(args.spec_path)
        width = find_result_width(hardware_spec)
        resolved = compute_unsigned_alu_outputs(
            hardware_spec=hardware_spec,
            operation=args.op,
            a_value=args.a,
            b_value=args.b,
            width=width,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in HardwareSpec file: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print("ERROR: HardwareSpec validation failed.", file=sys.stderr)
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error["loc"]) or "root"
            print(f"{location}: {error['msg']}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(resolved, indent=2, sort_keys=True))

    failures: list[str] = []
    if args.expect_result is not None and resolved.get("result") != args.expect_result:
        failures.append(f"Expected result={args.expect_result} but got {resolved.get('result')}.")
    if args.expect_carry is not None and resolved.get("carry") != args.expect_carry:
        failures.append(f"Expected carry={args.expect_carry} but got {resolved.get('carry')}.")
    if args.expect_zero is not None and resolved.get("zero") != args.expect_zero:
        failures.append(f"Expected zero={args.expect_zero} but got {resolved.get('zero')}.")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
