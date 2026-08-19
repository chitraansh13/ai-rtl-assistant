import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from pydantic import ValidationError

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.testbench_generation import (
    TestbenchGenerationResult,
    TestbenchGenerationStatus,
)
from rtl_assistant.models.verification_plan import VerificationPlan
from rtl_assistant.testbench.deterministic import DeterministicTestbenchGenerator


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for testbench generation."""

    parser = argparse.ArgumentParser(
        description="Generate a self-checking SystemVerilog testbench from a HardwareSpec and VerificationPlan."
    )
    parser.add_argument("spec_path", help="Path to the validated HardwareSpec JSON file.")
    parser.add_argument("plan_path", help="Path to the validated VerificationPlan JSON file.")
    parser.add_argument("--output", help="Optional path to save generated testbench.")
    return parser.parse_args()


def load_hardware_spec(spec_path_str: str) -> HardwareSpec:
    """Read and validate a HardwareSpec JSON file."""

    spec_path = Path(spec_path_str)
    if not spec_path.exists() or not spec_path.is_file():
        raise FileNotFoundError(f"HardwareSpec file not found or is not a file: {spec_path}")

    raw_json = spec_path.read_text(encoding="utf-8")
    json.loads(raw_json)
    return HardwareSpec.model_validate_json(raw_json)


def load_verification_plan(plan_path_str: str) -> VerificationPlan:
    """Read and validate a VerificationPlan JSON file."""

    plan_path = Path(plan_path_str)
    if not plan_path.exists() or not plan_path.is_file():
        raise FileNotFoundError(f"VerificationPlan file not found or is not a file: {plan_path}")

    raw_json = plan_path.read_text(encoding="utf-8")
    json.loads(raw_json)
    return VerificationPlan.model_validate_json(raw_json)


def print_success(result: TestbenchGenerationResult) -> None:
    """Print a concise successful generation summary."""

    print("========================================")
    print("Testbench Generator")
    print("========================================")
    print(f"Mode:           {result.generation_mode.value}")
    print(f"Attempts:       {result.attempts}")
    print(f"Status:         {result.status.value}")
    print("")
    print(f"Module:         {result.module_name}")
    if result.test_count is not None:
        print(f"Tests:          {result.test_count}")
    print("========================================")


def print_failure(result: TestbenchGenerationResult) -> None:
    """Print a concise failed generation summary."""

    print("========================================", file=sys.stderr)
    print("Testbench Generator", file=sys.stderr)
    print("========================================", file=sys.stderr)
    print(f"Mode:           {result.generation_mode.value}", file=sys.stderr)
    print(f"Attempts:       {result.attempts}", file=sys.stderr)
    print(f"Status:         {result.status.value}", file=sys.stderr)
    print(f"Error Type:     {result.error_type}", file=sys.stderr)
    print(f"Reason:         {result.error_message}", file=sys.stderr)
    if result.test_count is not None:
        print(f"Tests:          {result.test_count}", file=sys.stderr)
    if result.validation_errors:
        print("", file=sys.stderr)
        print("Validation Errors:", file=sys.stderr)
        for error in result.validation_errors:
            print(f"- {error}", file=sys.stderr)
    print("========================================", file=sys.stderr)


def write_output(output_path_str: str, result: TestbenchGenerationResult) -> None:
    """Write generated testbench text to a file."""

    testbench_text = result.testbench_text
    assert testbench_text is not None

    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(testbench_text, encoding="utf-8")
    print("")
    print("Generated testbench saved to:")
    print(output_path.resolve())


def main() -> int:
    args = parse_arguments()

    try:
        hardware_spec = load_hardware_spec(args.spec_path)
        verification_plan = load_verification_plan(args.plan_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON input file: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print("ERROR: Input validation failed.", file=sys.stderr)
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error["loc"]) or "root"
            print(f"{location}: {error['msg']}", file=sys.stderr)
        return 1

    generator = DeterministicTestbenchGenerator()
    result = generator.generate(hardware_spec, verification_plan)

    if result.status == TestbenchGenerationStatus.SUCCESS:
        print_success(result)
        if args.output:
            write_output(args.output, result)
        return 0

    print_failure(result)
    if args.output and Path(args.output).exists():
        print("Generation failed; existing output file was not modified.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
