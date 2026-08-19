import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from pydantic import ValidationError

from rtl_assistant.llm.config import get_default_ollama_base_url, get_default_ollama_model
from rtl_assistant.llm.ollama import OllamaProvider
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.verification_plan import (
    VerificationPlanGenerationResult,
    VerificationPlanStatus,
)
from rtl_assistant.verification_plan.generator import AIVerificationPlanGenerator


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for verification-plan generation."""

    parser = argparse.ArgumentParser(
        description="Generate a structured verification plan from a validated HardwareSpec JSON file."
    )
    parser.add_argument("spec_path", help="Path to the validated HardwareSpec JSON file.")
    parser.add_argument("--model", default=get_default_ollama_model(), help="Ollama model name.")
    parser.add_argument("--base-url", default=get_default_ollama_base_url(), help="Ollama base URL.")
    parser.add_argument("--output", help="Optional path to save the generated verification plan JSON.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw model output on failure.")
    return parser.parse_args()


def load_hardware_spec(spec_path_str: str) -> HardwareSpec:
    """Read and validate a HardwareSpec JSON file."""

    spec_path = Path(spec_path_str)
    if not spec_path.exists() or not spec_path.is_file():
        raise FileNotFoundError(f"HardwareSpec file not found or is not a file: {spec_path}")

    raw_json = spec_path.read_text(encoding="utf-8")
    json.loads(raw_json)
    return HardwareSpec.model_validate_json(raw_json)


def print_success(result: VerificationPlanGenerationResult) -> None:
    """Print a concise successful generation summary."""

    verification_plan = result.verification_plan
    assert verification_plan is not None

    print("========================================")
    print("AI Verification Plan Generator")
    print("========================================")
    print(f"Provider:       {result.provider}")
    print(f"Model:          {result.model}")
    print(f"Attempts:       {result.attempts}")
    print(f"Status:         {result.status.value}")
    print("")
    print(f"Module:         {result.module_name}")
    print(f"Test Cases:     {len(verification_plan.test_cases)}")
    if result.reference_corrections:
        print(f"Ref Corrections: {len(result.reference_corrections)}")
    if verification_plan.coverage_targets:
        print("")
        print("Coverage Targets:")
        for target in verification_plan.coverage_targets:
            print(f"- {target}")
    print("========================================")


def print_failure(result: VerificationPlanGenerationResult, show_raw: bool) -> None:
    """Print a concise failed generation summary."""

    print("========================================", file=sys.stderr)
    print("AI Verification Plan Generator", file=sys.stderr)
    print("========================================", file=sys.stderr)
    print(f"Provider:       {result.provider}", file=sys.stderr)
    print(f"Model:          {result.model}", file=sys.stderr)
    print(f"Attempts:       {result.attempts}", file=sys.stderr)
    print(f"Status:         {result.status.value}", file=sys.stderr)
    print(f"Error Type:     {result.error_type}", file=sys.stderr)
    print(f"Reason:         {result.error_message}", file=sys.stderr)
    if result.validation_errors:
        print("", file=sys.stderr)
        print("Validation Errors:", file=sys.stderr)
        for error in result.validation_errors:
            print(f"- {error}", file=sys.stderr)
    if show_raw and result.raw_model_output:
        print("\nRaw Model Output:", file=sys.stderr)
        print(result.raw_model_output, file=sys.stderr)
    print("========================================", file=sys.stderr)


def write_output(output_path_str: str, result: VerificationPlanGenerationResult) -> None:
    """Write the generated verification plan JSON to a file."""

    verification_plan = result.verification_plan
    assert verification_plan is not None

    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(verification_plan.model_dump_json(indent=2), encoding="utf-8")
    print("")
    print("Verification plan saved to:")
    print(output_path.resolve())


def main() -> int:
    args = parse_arguments()

    try:
        hardware_spec = load_hardware_spec(args.spec_path)
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

    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    generator = AIVerificationPlanGenerator(provider)
    result = generator.generate(hardware_spec)

    if result.status == VerificationPlanStatus.SUCCESS:
        print_success(result)
        if args.output:
            write_output(args.output, result)
        return 0

    print_failure(result, show_raw=args.show_raw)
    return 1


if __name__ == "__main__":
    sys.exit(main())
