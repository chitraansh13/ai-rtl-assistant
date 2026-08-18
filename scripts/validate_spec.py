import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from pydantic import ValidationError

from rtl_assistant.models.hardware_spec import HardwareSpec


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for spec validation."""

    parser = argparse.ArgumentParser(description="Validate a hardware specification JSON file.")
    parser.add_argument("spec_path", help="Path to the hardware specification JSON file.")
    return parser.parse_args()


def load_spec_json(spec_path: Path) -> str:
    """Read a spec file as raw JSON text."""

    if not spec_path.exists() or not spec_path.is_file():
        raise FileNotFoundError(f"Specification file not found or is not a file: {spec_path}")
    return spec_path.read_text(encoding="utf-8")


def print_summary(spec: HardwareSpec) -> None:
    """Print a concise validation summary."""

    print("========================================")
    print("Hardware Specification")
    print("========================================")
    print(f"Module:       {spec.module_name}")
    print(f"Type:         {spec.design_type.value}")
    print(f"Ports:        {len(spec.ports)}")
    print(f"Parameters:   {len(spec.parameters)}")

    if spec.clock is None:
        print("Clock:        none")
    else:
        print(f"Clock:        {spec.clock.signal} / {spec.clock.edge.value}")

    if spec.reset is None:
        print("Reset:        none")
    else:
        print(
            "Reset:        "
            f"{spec.reset.signal} / {spec.reset.type.value} / {spec.reset.polarity.value}"
        )

    print("")
    print("VALID HARDWARE SPEC")
    print("========================================")


def main() -> int:
    args = parse_arguments()
    spec_path = Path(args.spec_path)

    try:
        raw_json = load_spec_json(spec_path)
        json.loads(raw_json)
        spec = HardwareSpec.model_validate_json(raw_json)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print("INVALID HARDWARE SPEC", file=sys.stderr)
        print(f"JSON parse error: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print("INVALID HARDWARE SPEC", file=sys.stderr)
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error["loc"])
            print(f"{location}: {error['msg']}", file=sys.stderr)
        return 1

    print_summary(spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
