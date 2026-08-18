import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.llm.ollama import OllamaProvider
from rtl_assistant.models.llm import RequirementParseResult, RequirementStatus
from rtl_assistant.spec.ai_parser import AIRequirementParser, apply_clarifications


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for AI requirement parsing."""

    parser = argparse.ArgumentParser(description="Parse a natural-language hardware requirement into HardwareSpec.")
    parser.add_argument("requirement", help="Natural-language hardware requirement text.")
    parser.add_argument("--model", default="qwen2.5-coder:7b", help="Ollama model name.")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")
    parser.add_argument("--output", help="Optional path to write the validated HardwareSpec JSON.")
    parser.add_argument("--answers", help="Optional JSON file containing clarification answers.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw model output on failure.")
    return parser.parse_args()


def load_answers(answers_path_str: str) -> dict[str, str]:
    """Load clarification answers from a JSON file."""

    answers_path = Path(answers_path_str)
    if not answers_path.exists() or not answers_path.is_file():
        raise FileNotFoundError(f"Answers file not found or is not a file: {answers_path}")

    raw_text = answers_path.read_text(encoding="utf-8")
    parsed = json.loads(raw_text)
    if not isinstance(parsed, dict):
        raise ValueError("Answers JSON must be an object mapping clarification ids to strings.")

    normalized: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Each clarification answer key must be a non-empty string.")
        normalized[key.strip()] = str(value).strip()

    return normalized


def print_ready(result: RequirementParseResult) -> None:
    """Print a concise success summary."""

    spec = result.hardware_spec
    assert spec is not None

    print("========================================")
    print("AI Requirement Parser")
    print("========================================")
    print(f"Provider:      {result.provider}")
    print(f"Model:         {result.model}")
    print(f"Attempts:      {result.attempts}")
    print("Status:        READY")
    print("")
    print(f"Module:        {spec.module_name}")
    print(f"Type:          {spec.design_type.value}")
    print(f"Ports:         {len(spec.ports)}")
    if spec.clock is None:
        print("Clock:         none")
    else:
        print(f"Clock:         {spec.clock.signal} / {spec.clock.edge.value}")
    if spec.reset is None:
        print("Reset:         none")
    else:
        print(f"Reset:         {spec.reset.signal} / {spec.reset.type.value} / {spec.reset.polarity.value}")
    print("")
    print("VALID HARDWARE SPEC")
    print("========================================")


def print_needs_clarification(result: RequirementParseResult) -> None:
    """Print structured clarification questions for ambiguous requirements."""

    print("========================================")
    print("AI Requirement Parser")
    print("========================================")
    print(f"Provider:      {result.provider}")
    print(f"Model:         {result.model}")
    print(f"Attempts:      {result.attempts}")
    print("Status:        NEEDS_CLARIFICATION")
    print("")
    print("The requirement is missing important hardware details:")
    print("")
    for index, question in enumerate(result.clarification_questions, start=1):
        print(f"{index}. {question.question}")
        print(f"   Reason: {question.reason}")
        if question.choices:
            print(f"   Choices: {' / '.join(question.choices)}")
        if question.default is not None:
            print(f"   Default: {question.default}")
        print("")

    if result.assumptions:
        print("Current noncritical assumptions:")
        for assumption in result.assumptions:
            print(f"- {assumption}")
        print("")

    if result.unresolved_fields:
        print("Unresolved fields:")
        for field in result.unresolved_fields:
            print(f"- {field}")
        print("")

    print("No final HardwareSpec was generated.")
    print("========================================")


def print_failure(result: RequirementParseResult, show_raw: bool) -> None:
    """Print a concise failure summary."""

    print("========================================", file=sys.stderr)
    print("AI Requirement Parser", file=sys.stderr)
    print("========================================", file=sys.stderr)
    print(f"Provider:      {result.provider}", file=sys.stderr)
    print(f"Model:         {result.model}", file=sys.stderr)
    print(f"Attempts:      {result.attempts}", file=sys.stderr)
    print("Status:        FAIL", file=sys.stderr)
    print(f"Error Type:    {result.error_type}", file=sys.stderr)
    print(f"Reason:        {result.error_message}", file=sys.stderr)

    if result.validation_errors:
        print("\nValidation Errors:", file=sys.stderr)
        for error in result.validation_errors:
            print(f"  {error}", file=sys.stderr)

    if result.assumptions:
        print("\nAssumptions:", file=sys.stderr)
        for assumption in result.assumptions:
            print(f"  {assumption}", file=sys.stderr)

    if show_raw and result.raw_model_output.strip():
        print("\nRaw Model Output:", file=sys.stderr)
        print(result.raw_model_output, file=sys.stderr)

    print("========================================", file=sys.stderr)


def write_output(output_path_str: str, result: RequirementParseResult) -> None:
    """Write the validated HardwareSpec to a JSON file."""

    spec = result.hardware_spec
    assert spec is not None

    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    print(f"HardwareSpec saved to: {output_path.resolve()}")


def status_to_exit_code(status: RequirementStatus) -> int:
    """Map parser status to CLI exit code."""

    if status == RequirementStatus.READY:
        return 0
    if status == RequirementStatus.NEEDS_CLARIFICATION:
        return 2
    return 1


def main() -> int:
    args = parse_arguments()
    requirement = args.requirement

    if args.answers:
        try:
            answers = load_answers(args.answers)
            requirement = apply_clarifications(requirement, answers)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    parser = AIRequirementParser(provider)
    result = parser.parse(requirement)

    if result.status == RequirementStatus.READY:
        print_ready(result)
        if args.output:
            write_output(args.output, result)
    elif result.status == RequirementStatus.NEEDS_CLARIFICATION:
        print_needs_clarification(result)
    else:
        print_failure(result, show_raw=args.show_raw)

    return status_to_exit_code(result.status)


if __name__ == "__main__":
    sys.exit(main())
