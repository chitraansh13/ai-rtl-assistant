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
        description="Generate AI verification intent and a compiled verification plan from a validated HardwareSpec JSON file."
    )
    parser.add_argument("spec_path", help="Path to the validated HardwareSpec JSON file.")
    parser.add_argument("--model", default=get_default_ollama_model(), help="Ollama model name.")
    parser.add_argument("--base-url", default=get_default_ollama_base_url(), help="Ollama base URL.")
    parser.add_argument("--output", help="Optional path to save the compiled verification plan JSON.")
    parser.add_argument("--intent-output", help="Optional path to save the raw verification intent JSON.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw model output on failure.")
    parser.add_argument(
        "--show-raw-intent",
        action="store_true",
        help="Print the validated verification intent on success, or the final raw model response on AI-generation failure.",
    )
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

    verification_intent = result.verification_intent
    compiled_plan = result.compiled_plan
    assert verification_intent is not None
    assert compiled_plan is not None

    print("========================================")
    print("AI Verification Plan Generator")
    print("========================================")
    print(f"Provider:       {result.provider}")
    print(f"Model:          {result.model}")
    print(f"Attempts:       {result.attempts}")
    print(f"Status:         {result.status.value}")
    print("")
    print(f"Module:         {result.module_name}")
    print(f"Intent Cases:   {len(verification_intent.cases)}")
    print(f"Compiled Cases: {len(compiled_plan.cases)}")
    if compiled_plan.coverage_targets:
        print("")
        print("Coverage Targets:")
        for target in compiled_plan.coverage_targets:
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


def print_raw_intent_failure(result: VerificationPlanGenerationResult) -> None:
    """Print the final raw model response that caused AI verification-intent failure."""

    if not result.raw_model_output:
        return
    print("", file=sys.stderr)
    print("Final Raw Verification Intent Response:", file=sys.stderr)
    print(result.raw_model_output, file=sys.stderr)


def write_output(output_path_str: str, result: VerificationPlanGenerationResult) -> None:
    """Write the compiled verification plan JSON to a file."""

    compiled_plan = result.compiled_plan
    assert compiled_plan is not None

    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(compiled_plan.model_dump_json(indent=2), encoding="utf-8")
    print("")
    print("Compiled verification plan saved to:")
    print(output_path.resolve())


def write_intent_output(output_path_str: str, result: VerificationPlanGenerationResult) -> None:
    """Write the generated verification intent JSON to a file."""

    verification_intent = result.verification_intent
    assert verification_intent is not None

    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(verification_intent.model_dump_json(indent=2), encoding="utf-8")
    print("")
    print("Verification intent saved to:")
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
        if args.show_raw_intent and result.verification_intent is not None:
            print("")
            print("Verification Intent:")
            print(result.verification_intent.model_dump_json(indent=2))
        if args.output:
            write_output(args.output, result)
        if args.intent_output:
            write_intent_output(args.intent_output, result)
        return 0

    print_failure(result, show_raw=args.show_raw)
    if args.show_raw_intent:
        print_raw_intent_failure(result)
    return 1


if __name__ == "__main__":
    sys.exit(main())
