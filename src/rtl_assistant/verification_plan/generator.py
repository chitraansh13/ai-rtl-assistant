import json
import time

from pydantic import ValidationError

from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.verification_intent import VerificationIntentPlan
from rtl_assistant.models.verification_plan import (
    VerificationPlanGenerationResult,
    VerificationPlanStatus,
)
from rtl_assistant.verification_plan.compiler import (
    VerificationCompilationError,
    compile_verification_intent_plan,
)
from rtl_assistant.verification_plan.prompts import (
    VERIFICATION_PLAN_PROMPT_VERSION,
    build_verification_plan_prompt,
    build_verification_plan_repair_prompt,
)


class AIVerificationPlanGenerator:
    """Generate verification intent with AI and compile it deterministically."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def generate(self, hardware_spec: HardwareSpec) -> VerificationPlanGenerationResult:
        """Generate intent, compile it, and return the executable compiled plan."""

        started_at = time.perf_counter()
        validation_errors: list[str] = []
        raw_model_output = ""

        for attempt_number in range(1, 3):
            prompt = (
                build_verification_plan_prompt(hardware_spec)
                if attempt_number == 1
                else build_verification_plan_repair_prompt(hardware_spec, raw_model_output, validation_errors)
            )
            llm_response = self.provider.generate(prompt)
            raw_model_output = llm_response.response_text

            if not llm_response.success:
                return VerificationPlanGenerationResult(
                    status=VerificationPlanStatus.FAIL,
                    module_name=hardware_spec.module_name,
                    verification_intent=None,
                    compiled_plan=None,
                    verification_plan=None,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    prompt_version=VERIFICATION_PLAN_PROMPT_VERSION,
                    attempts=attempt_number,
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    raw_model_output=raw_model_output or None,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                    validation_errors=validation_errors,
                    reference_corrections=[],
                )

            json_object, json_error = extract_json_object(raw_model_output)
            if json_error is not None:
                validation_errors = [json_error]
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec,
                        attempt_number,
                        raw_model_output,
                        validation_errors,
                        started_at,
                        error_type="INVALID_PLAN_JSON",
                        error_message="Model output was not valid verification-intent JSON after retry.",
                    )
                continue

            normalized_payload = normalize_verification_intent_payload(json_object)

            envelope_errors = validate_verification_intent_envelope(normalized_payload)
            if envelope_errors:
                validation_errors = envelope_errors
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec,
                        attempt_number,
                        raw_model_output,
                        validation_errors,
                        started_at,
                        error_type="INVALID_VERIFICATION_INTENT_ENVELOPE",
                        error_message="Model output did not contain the complete VerificationIntentPlan envelope after retry.",
                    )
                continue

            try:
                verification_intent = VerificationIntentPlan.model_validate(normalized_payload)
            except ValidationError as exc:
                validation_errors = format_validation_errors(exc)
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec,
                        attempt_number,
                        raw_model_output,
                        validation_errors,
                        started_at,
                        error_type="VERIFICATION_INTENT_VALIDATION_FAILED",
                        error_message="Model output JSON did not satisfy the VerificationIntentPlan schema after retry.",
                    )
                continue

            try:
                compiled_plan = compile_verification_intent_plan(hardware_spec, verification_intent)
            except VerificationCompilationError as exc:
                validation_errors = [f"{exc.error_type}: {exc.message}"]
                if attempt_number == 2:
                    return self._failure_result(
                        hardware_spec,
                        attempt_number,
                        raw_model_output,
                        validation_errors,
                        started_at,
                        error_type=exc.error_type,
                        error_message=exc.message,
                    )
                continue

            return VerificationPlanGenerationResult(
                status=VerificationPlanStatus.SUCCESS,
                module_name=hardware_spec.module_name,
                verification_intent=verification_intent,
                compiled_plan=compiled_plan,
                verification_plan=None,
                provider=llm_response.provider,
                model=llm_response.model,
                prompt_version=VERIFICATION_PLAN_PROMPT_VERSION,
                attempts=attempt_number,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                raw_model_output=raw_model_output,
                error_type=None,
                error_message=None,
                validation_errors=[],
                reference_corrections=[],
            )

        return self._failure_result(
            hardware_spec,
            2,
            raw_model_output,
            ["Verification-intent generation exhausted its retry budget."],
            started_at,
            error_type="VERIFICATION_PLAN_RETRY_EXHAUSTED",
            error_message="Verification-intent generation exhausted its retry budget.",
        )

    def _failure_result(
        self,
        hardware_spec: HardwareSpec,
        attempts: int,
        raw_model_output: str,
        validation_errors: list[str],
        started_at: float,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> VerificationPlanGenerationResult:
        """Build a structured failure result."""

        resolved_error_type = error_type or derive_primary_error_type(validation_errors)
        resolved_error_message = error_message or (
            validation_errors[0] if validation_errors else "Verification-intent generation failed."
        )
        return VerificationPlanGenerationResult(
            status=VerificationPlanStatus.FAIL,
            module_name=hardware_spec.module_name,
            verification_intent=None,
            compiled_plan=None,
            verification_plan=None,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            prompt_version=VERIFICATION_PLAN_PROMPT_VERSION,
            attempts=attempts,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            raw_model_output=raw_model_output or None,
            error_type=resolved_error_type,
            error_message=resolved_error_message,
            validation_errors=validation_errors,
            reference_corrections=[],
        )


def extract_json_object(text: str) -> tuple[dict | None, str | None]:
    """Extract a top-level JSON object from raw LLM text."""

    stripped = text.strip()
    if not stripped:
        return None, "Model output was empty."

    try:
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            return None, "Model output must decode to a top-level JSON object."
        return parsed, None
    except json.JSONDecodeError:
        pass

    fenced = strip_single_markdown_fence(stripped)
    candidate_texts = [candidate for candidate in (fenced, stripped) if candidate]

    last_error: str | None = None
    for candidate in candidate_texts:
        extracted = extract_first_json_object_text(candidate)
        if extracted is None:
            continue
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError as exc:
            last_error = f"Model output was not valid JSON: {exc}"
            continue
        if not isinstance(parsed, dict):
            return None, "Model output must decode to a top-level JSON object."
        return parsed, None

    return None, last_error or "Model output was not valid JSON."


def extract_first_json_object_text(text: str) -> str | None:
    """Extract the first balanced top-level JSON object from surrounding prose."""

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, end_index = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return text[index : index + end_index]
    return None


def normalize_verification_intent_payload(payload: dict) -> dict:
    """Repair small representation mismatches before strict intent validation."""

    normalized = {
        key.strip() if isinstance(key, str) else key: value
        for key, value in dict(payload).items()
    }
    normalized["coverage_targets"] = normalize_string_list(normalized.get("coverage_targets"))
    normalized["assumptions"] = normalize_string_list(normalized.get("assumptions"))
    normalized["notes"] = normalize_string_list(normalized.get("notes"))

    raw_cases = normalized.get("cases")
    if isinstance(raw_cases, list):
        normalized_cases: list[object] = []
        for item in raw_cases:
            if not isinstance(item, dict):
                normalized_cases.append(item)
                continue

            case_payload = {
                key.strip() if isinstance(key, str) else key: value
                for key, value in dict(item).items()
            }
            case_payload["coverage_tags"] = normalize_string_list(case_payload.get("coverage_tags"))
            case_payload["notes"] = normalize_string_list(case_payload.get("notes"))
            precondition = case_payload.get("precondition_intent")
            if isinstance(precondition, str) and precondition.strip():
                case_payload["precondition_intent"] = {
                    "kind": "LEGAL_PRECONDITION",
                    "description": precondition.strip(),
                }
            elif precondition is None:
                case_payload["precondition_intent"] = None
            normalized_cases.append(case_payload)
        normalized["cases"] = normalized_cases

    return normalized


def validate_verification_intent_envelope(payload: dict) -> list[str]:
    """Check that the extracted JSON still contains the required top-level intent envelope."""

    required_fields = [
        "schema_version",
        "module_name",
        "design_type",
        "strategy",
        "cases",
        "coverage_targets",
        "assumptions",
        "notes",
    ]
    missing = [field_name for field_name in required_fields if field_name not in payload]
    if not missing:
        return []
    return [
        "INVALID_VERIFICATION_INTENT_ENVELOPE: Return the complete VerificationIntentPlan JSON object with all "
        f"required top-level fields. Missing: {', '.join(missing)}. Present keys: {', '.join(str(key) for key in payload.keys()) or '(none)'}"
    ]


def normalize_string_list(value: object) -> object:
    """Normalize obvious scalar-or-bulleted encodings into a list of strings."""

    if value is None:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        if len(lines) > 1 and all(line.startswith(("-", "*")) for line in lines):
            return [line[1:].strip() for line in lines if line[1:].strip()]
        return [stripped]
    return value


def strip_single_markdown_fence(text: str) -> str | None:
    """Strip one outer Markdown fence when present."""

    if not text.startswith("```"):
        return None

    lines = text.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return None
    return "\n".join(lines[1:-1]).strip()


def format_validation_errors(exc: ValidationError) -> list[str]:
    """Render Pydantic validation errors into readable strings."""

    errors: list[str] = []
    for error in exc.errors():
        location = " -> ".join(str(part) for part in error["loc"]) or "root"
        errors.append(f"{location}: {error['msg']}")
    return errors


def derive_primary_error_type(errors: list[str]) -> str:
    """Extract a structured error prefix from one list of failures."""

    if not errors:
        return "VERIFICATION_PLAN_GENERATION_FAILED"
    return errors[0].split(":", 1)[0].strip() or "VERIFICATION_PLAN_GENERATION_FAILED"
