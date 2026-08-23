import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.llm.config import get_default_ollama_base_url, get_default_ollama_model
from rtl_assistant.llm.ollama import OllamaProvider
from rtl_assistant.models.llm import RequirementParseResult, RequirementStatus
from rtl_assistant.spec.ai_parser import (
    AIRequirementParser,
    AcceptedClarificationAnswer,
    AnalyzedRequirement,
    build_enriched_requirement,
    normalize_clarification_answer_value,
    question_identity,
    validate_clarification_answers,
)

MAX_CLARIFICATION_ROUNDS = 5


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for AI requirement parsing."""

    parser = argparse.ArgumentParser(description="Parse a natural-language hardware requirement into HardwareSpec.")
    parser.add_argument("requirement", help="Natural-language hardware requirement text.")
    parser.add_argument("--model", default=get_default_ollama_model(), help="Ollama model name.")
    parser.add_argument("--base-url", default=get_default_ollama_base_url(), help="Ollama base URL.")
    parser.add_argument("--output", help="Optional path to write the validated HardwareSpec JSON.")
    parser.add_argument("--answers", help="Optional JSON file containing clarification answers.")
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable interactive clarification prompts and return NEEDS_CLARIFICATION instead.",
    )
    parser.add_argument(
        "--show-enriched-requirement",
        action="store_true",
        help="Print the deterministic enriched requirement used after clarification answers are applied.",
    )
    parser.add_argument(
        "--show-intent",
        action="store_true",
        help="Print the exact validated HardwareIntent consumed by deterministic semantic compilation.",
    )
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


def print_interactive_questions(questions: list, *, prefix: str | None = None) -> None:
    """Print the current clarification questions for one interactive round."""

    if prefix:
        print(prefix)
    for index, question in enumerate(questions, start=1):
        print(f"{index}. {question.question}")
        print(f"   Reason: {question.reason}")
        if question.choices:
            for choice_index, choice in enumerate(question.choices, start=1):
                print(f"   {choice_index}. {choice}")
        if question.default is not None:
            print(f"   Default: {question.default}")
        print("")


def print_interactive_clarification_round(result: RequirementParseResult) -> None:
    """Print one interactive clarification round with numbered choices suitable for stdin prompts."""

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
    print_interactive_questions(result.clarification_questions)


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


def print_enriched_requirement(enriched_requirement: str, title: str = "Final Enriched Requirement") -> None:
    """Print the deterministic enriched requirement used for the clarified parse pass."""

    print("========================================")
    print(title)
    print("========================================")
    print(enriched_requirement)
    print("========================================")


def print_hardware_intent(intent) -> None:
    """Print the exact validated HardwareIntent passed into deterministic semantic compilation."""

    print("========================================")
    print("Validated Hardware Intent")
    print("========================================")
    print(intent.model_dump_json(indent=2))
    print("========================================")


def print_raw_hardware_intent_failure(raw_model_output: str) -> None:
    """Print the final raw HardwareIntent response that failed validation or lowering."""

    if not raw_model_output.strip():
        return
    print("", file=sys.stderr)
    print("Final Raw Hardware Intent Response:", file=sys.stderr)
    print(raw_model_output, file=sys.stderr)


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


def make_failure_result(
    requirement: str,
    *,
    provider: str | None,
    model: str | None,
    attempts: int,
    error_type: str,
    error_message: str,
    raw_model_output: str = "",
    assumptions: list[str] | None = None,
) -> RequirementParseResult:
    """Construct one structured CLI failure result."""

    return RequirementParseResult(
        requirement=requirement,
        status=RequirementStatus.FAIL,
        hardware_spec=None,
        clarification_questions=[],
        unresolved_fields=[],
        assumptions=list(assumptions or []),
        raw_model_output=raw_model_output,
        provider=provider,
        model=model,
        attempts=max(1, attempts),
        validation_errors=[],
        error_type=error_type,
        error_message=error_message,
        duration_ms=None,
    )


def answers_map_to_list(accepted_answers: dict[str, str]) -> list[AcceptedClarificationAnswer]:
    """Convert the canonical accepted-answer map into the parser's typed answer list."""

    return [
        AcceptedClarificationAnswer(semantic_key=semantic_key, value=value)
        for semantic_key, value in accepted_answers.items()
    ]


def rebuild_effective_requirement(
    original_requirement: str,
    accepted_answers: dict[str, str],
    known_questions: dict[str, object],
) -> str:
    """Rebuild the authoritative effective requirement from the original requirement plus all accepted facts."""

    if not accepted_answers:
        return original_requirement.strip()
    return build_enriched_requirement(
        original_requirement=original_requirement,
        accepted_answers=answers_map_to_list(accepted_answers),
        clarification_questions=list(known_questions.values()),
    )


def existing_answer_matches_question(existing_answer: str, question: object) -> bool:
    """Check whether one previously accepted answer still satisfies the current question contract."""

    try:
        normalize_clarification_answer_value(existing_answer, question)
    except ValueError:
        return False
    return True


def ensure_question_contract_compatible(existing_question: object, new_question: object) -> None:
    """Reject incompatible clarification contracts for the same semantic identity."""

    existing_choices = [choice.strip().casefold() for choice in getattr(existing_question, "choices", [])]
    new_choices = [choice.strip().casefold() for choice in getattr(new_question, "choices", [])]
    if existing_choices and new_choices and existing_choices != new_choices:
        raise ValueError(
            f"Clarification question '{question_identity(new_question)}' was reintroduced with incompatible choices."
        )


def filter_pending_questions(
    questions: list,
    accepted_answers: dict[str, str],
    known_questions: dict[str, object],
) -> list:
    """Return only the clarification questions that are not already resolved by accepted answers."""

    pending: list = []
    for question in questions:
        identity = question_identity(question)
        existing_question = known_questions.get(identity)
        if existing_question is not None:
            ensure_question_contract_compatible(existing_question, question)
        else:
            known_questions[identity] = question

        existing_answer = accepted_answers.get(identity)
        if existing_answer is not None:
            if not existing_answer_matches_question(existing_answer, question):
                raise ValueError(
                    f"Previously accepted answer for '{identity}' is incompatible with the current clarification contract."
                )
            continue
        pending.append(question)
    return pending


def collect_answers_interactively(questions: list) -> dict[str, str]:
    """Collect one clarification round interactively from stdin."""

    answers: dict[str, str] = {}
    for question in questions:
        prompt_label = "Choice" if question.choices else "Answer"
        if question.default is not None:
            prompt_label += f" [default: {question.default}]"
        prompt_label += ": "

        while True:
            try:
                raw_value = input(prompt_label)
            except (KeyboardInterrupt, EOFError) as exc:
                raise exc

            stripped = raw_value.strip()
            candidate = stripped
            if not candidate and question.default is not None:
                candidate = question.default

            if question.choices and candidate.isdigit():
                index = int(candidate)
                if 1 <= index <= len(question.choices):
                    candidate = question.choices[index - 1]
                else:
                    print(f"Invalid choice. Enter 1-{len(question.choices)}.")
                    continue

            try:
                answers[question_identity(question)] = normalize_clarification_answer_value(candidate, question)
                break
            except ValueError:
                if question.choices:
                    print(f"Invalid choice. Enter 1-{len(question.choices)} or the exact choice text.")
                else:
                    print("Invalid answer. Enter a non-empty value.")
    return answers


def merge_accepted_answers(
    accepted_answers: dict[str, str],
    new_answers: list[AcceptedClarificationAnswer],
) -> None:
    """Merge one round of accepted answers into the accumulated canonical answer map."""

    for answer in new_answers:
        existing = accepted_answers.get(answer.semantic_key)
        if existing is not None and existing != answer.value:
            raise ValueError(
                f"Clarification answer for '{answer.semantic_key}' conflicts with a previously accepted answer."
            )
        accepted_answers[answer.semantic_key] = answer.value


def prepare_render_result(result: RequirementParseResult, pending_questions: list) -> RequirementParseResult:
    """Build a renderable clarification result that only shows the currently unresolved questions."""

    unresolved_fields = list(dict.fromkeys([question_identity(question) for question in pending_questions]))
    return result.model_copy(
        update={
            "clarification_questions": pending_questions,
            "unresolved_fields": unresolved_fields,
        }
    )


def main() -> int:
    args = parse_arguments()
    original_requirement = args.requirement.strip()
    effective_requirement = original_requirement
    supplied_answers: dict[str, str] | None = None
    accepted_answers: dict[str, str] = {}
    known_questions: dict[str, object] = {}
    final_enriched_requirement_shown = False

    if args.answers:
        try:
            supplied_answers = load_answers(args.answers)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    parser = AIRequirementParser(provider)
    interactive_enabled = supplied_answers is None and not args.no_interactive and sys.stdin.isatty()
    clarification_rounds = 0

    while True:
        if clarification_rounds >= MAX_CLARIFICATION_ROUNDS:
            result = make_failure_result(
                original_requirement,
                provider=provider.provider_name,
                model=provider.model_name,
                attempts=1,
                error_type="CLARIFICATION_LIMIT_EXCEEDED",
                error_message=f"Clarification exceeded the maximum of {MAX_CLARIFICATION_ROUNDS} rounds.",
            )
            break

        analysis_or_result = parser.analyze_requirement(effective_requirement)
        if isinstance(analysis_or_result, AnalyzedRequirement):
            if supplied_answers is not None and not accepted_answers:
                result = make_failure_result(
                    original_requirement,
                    provider=provider.provider_name,
                    model=provider.model_name,
                    attempts=analysis_or_result.attempts,
                    error_type="UNEXPECTED_CLARIFICATION_ANSWERS",
                    error_message="Clarification answers were provided, but the requirement did not require clarification.",
                    raw_model_output=analysis_or_result.raw_model_output,
                    assumptions=analysis_or_result.analysis.assumptions,
                )
                break

            if args.show_enriched_requirement and effective_requirement != original_requirement:
                print_enriched_requirement(effective_requirement, title="Final Enriched Requirement")
                final_enriched_requirement_shown = True

            print("Generating Hardware Intent...")
            print("Compiling semantic intent...")
            result = parser.generate_hardware_spec(analysis_or_result)
            if args.show_intent:
                hardware_intent = parser.get_last_validated_hardware_intent()
                if hardware_intent is not None:
                    print_hardware_intent(hardware_intent)
            break

        result = analysis_or_result
        if result.status == RequirementStatus.FAIL:
            break

        try:
            pending_questions = filter_pending_questions(
                result.clarification_questions,
                accepted_answers=accepted_answers,
                known_questions=known_questions,
            )
        except ValueError as exc:
            result = make_failure_result(
                original_requirement,
                provider=result.provider,
                model=result.model,
                attempts=result.attempts,
                error_type="CLARIFICATION_CONTRACT_CONFLICT",
                error_message=str(exc),
                raw_model_output=result.raw_model_output,
                assumptions=result.assumptions,
            )
            break

        if supplied_answers is not None:
            if not pending_questions:
                result = make_failure_result(
                    original_requirement,
                    provider=result.provider,
                    model=result.model,
                    attempts=result.attempts,
                    error_type="CLARIFICATION_STALLED",
                    error_message="No new clarification questions remained after applying existing answers, but ambiguity still remained.",
                    raw_model_output=result.raw_model_output,
                    assumptions=result.assumptions,
                )
                break

            try:
                round_answers = validate_clarification_answers(
                    original_requirement=effective_requirement,
                    answers=supplied_answers,
                    clarification_questions=pending_questions,
                )
                merge_accepted_answers(accepted_answers, round_answers)
            except ValueError as exc:
                result = make_failure_result(
                    original_requirement,
                    provider=result.provider,
                    model=result.model,
                    attempts=result.attempts,
                    error_type="INVALID_CLARIFICATION_ANSWERS",
                    error_message=str(exc),
                    raw_model_output=result.raw_model_output,
                    assumptions=result.assumptions,
                )
                break

            effective_requirement = rebuild_effective_requirement(
                original_requirement,
                accepted_answers=accepted_answers,
                known_questions=known_questions,
            )
            if round_answers and effective_requirement.strip() == original_requirement.strip():
                result = make_failure_result(
                    original_requirement,
                    provider=result.provider,
                    model=result.model,
                    attempts=result.attempts,
                    error_type="CLARIFICATION_ENRICHMENT_FAILED",
                    error_message=(
                        "Clarification answers were accepted, but the enriched requirement remained identical to the original requirement."
                    ),
                    raw_model_output=result.raw_model_output,
                    assumptions=result.assumptions,
                )
                break

            supplied_answers = None
            clarification_rounds += 1
            continue

        if not interactive_enabled:
            result = prepare_render_result(result, pending_questions)
            break

        if not pending_questions:
            result = make_failure_result(
                original_requirement,
                provider=result.provider,
                model=result.model,
                attempts=result.attempts,
                error_type="CLARIFICATION_STALLED",
                error_message="Ambiguity remains, but there are no new clarification questions to ask.",
                raw_model_output=result.raw_model_output,
                assumptions=result.assumptions,
            )
            break

        result = prepare_render_result(result, pending_questions)
        print_interactive_clarification_round(result)
        try:
            round_answer_map = collect_answers_interactively(pending_questions)
        except KeyboardInterrupt:
            print("\nClarification cancelled by user.", file=sys.stderr)
            return 130
        except EOFError:
            print("\nClarification cancelled due to end-of-input.", file=sys.stderr)
            return 130

        try:
            round_answers = validate_clarification_answers(
                original_requirement=effective_requirement,
                answers=round_answer_map,
                clarification_questions=pending_questions,
            )
            merge_accepted_answers(accepted_answers, round_answers)
        except ValueError as exc:
            result = make_failure_result(
                original_requirement,
                provider=result.provider,
                model=result.model,
                attempts=result.attempts,
                error_type="INVALID_CLARIFICATION_ANSWERS",
                error_message=str(exc),
                raw_model_output=result.raw_model_output,
                assumptions=result.assumptions,
            )
            break

        effective_requirement = rebuild_effective_requirement(
            original_requirement,
            accepted_answers=accepted_answers,
            known_questions=known_questions,
        )
        if round_answers and effective_requirement.strip() == original_requirement.strip():
            result = make_failure_result(
                original_requirement,
                provider=result.provider,
                model=result.model,
                attempts=result.attempts,
                error_type="CLARIFICATION_ENRICHMENT_FAILED",
                error_message=(
                    "Clarification answers were accepted, but the enriched requirement remained identical to the original requirement."
                ),
                raw_model_output=result.raw_model_output,
                assumptions=result.assumptions,
            )
            break

        clarification_rounds += 1
        print("Analyzing clarified requirement...")

    if result.status == RequirementStatus.READY:
        print_ready(result)
        if args.output:
            write_output(args.output, result)
    elif result.status == RequirementStatus.NEEDS_CLARIFICATION:
        if args.show_enriched_requirement and not final_enriched_requirement_shown and effective_requirement != original_requirement:
            print_enriched_requirement(effective_requirement, title="Current Enriched Requirement")
        print_needs_clarification(result)
    else:
        if args.show_enriched_requirement and not final_enriched_requirement_shown and effective_requirement != original_requirement:
            print_enriched_requirement(effective_requirement, title="Current Enriched Requirement")
        print_failure(result, show_raw=args.show_raw)
        if args.show_intent:
            hardware_intent = parser.get_last_validated_hardware_intent()
            if hardware_intent is None:
                print_raw_hardware_intent_failure(result.raw_model_output)

    return status_to_exit_code(result.status)


if __name__ == "__main__":
    sys.exit(main())
