import re
import time

from rtl_assistant.llm.base import LLMProvider
from rtl_assistant.models.hardware_spec import DesignType, HardwareSpec
from rtl_assistant.models.rtl_generation import RTLGenerationResult, RTLGenerationStatus
from rtl_assistant.rtl.prompts import (
    RTL_GENERATION_PROMPT_VERSION,
    build_rtl_generation_prompt,
    build_rtl_repair_prompt,
)

FORBIDDEN_CONSTRUCT_PATTERNS: list[tuple[str, str]] = [
    (r"\$display\b", "$display"),
    (r"\$finish\b", "$finish"),
    (r"\$dumpfile\b", "$dumpfile"),
    (r"\$dumpvars\b", "$dumpvars"),
    (r"(^|\s)#\s*\d+", "#delay"),
    (r"\binitial\s+begin\b", "initial begin"),
]


class AIRTLGenerator:
    """Generate SystemVerilog RTL from a validated HardwareSpec using a provider-neutral LLM interface."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def generate(self, hardware_spec: HardwareSpec) -> RTLGenerationResult:
        """Generate RTL with up to two attempts and lightweight local sanity checking."""

        started_at = time.perf_counter()
        raw_model_output = ""
        errors: list[str] = []

        for attempt_number in range(1, 3):
            if attempt_number == 1:
                prompt = build_rtl_generation_prompt(hardware_spec)
            else:
                prompt = build_rtl_repair_prompt(hardware_spec, raw_model_output, errors)

            llm_response = self.provider.generate(prompt)
            raw_model_output = llm_response.response_text

            if not llm_response.success:
                return RTLGenerationResult(
                    status=RTLGenerationStatus.FAIL,
                    module_name=hardware_spec.module_name,
                    rtl=None,
                    provider=llm_response.provider,
                    model=llm_response.model,
                    prompt_version=RTL_GENERATION_PROMPT_VERSION,
                    attempts=attempt_number,
                    duration_ms=int((time.perf_counter() - started_at) * 1000),
                    raw_model_output=raw_model_output or None,
                    error_type=llm_response.error_type,
                    error_message=llm_response.error_message,
                )

            rtl_text, extract_errors = extract_rtl_module(raw_model_output)
            if rtl_text is None:
                errors = extract_errors
                if attempt_number == 2:
                    return self._failure_result(hardware_spec, attempt_number, raw_model_output, errors, started_at)
                continue

            errors = run_rtl_sanity_checks(hardware_spec, rtl_text)
            if errors:
                if attempt_number == 2:
                    return self._failure_result(hardware_spec, attempt_number, raw_model_output, errors, started_at)
                continue

            return RTLGenerationResult(
                status=RTLGenerationStatus.SUCCESS,
                module_name=hardware_spec.module_name,
                rtl=rtl_text,
                provider=llm_response.provider,
                model=llm_response.model,
                prompt_version=RTL_GENERATION_PROMPT_VERSION,
                attempts=attempt_number,
                duration_ms=int((time.perf_counter() - started_at) * 1000),
                raw_model_output=raw_model_output,
                error_type=None,
                error_message=None,
            )

        return self._failure_result(
            hardware_spec,
            2,
            raw_model_output,
            ["RTL generation exhausted its retry budget."],
            started_at,
            error_type="RTL_GENERATION_RETRY_EXHAUSTED",
        )

    def _failure_result(
        self,
        hardware_spec: HardwareSpec,
        attempts: int,
        raw_model_output: str,
        errors: list[str],
        started_at: float,
        error_type: str | None = None,
    ) -> RTLGenerationResult:
        """Build a structured failure result from local extraction or sanity errors."""

        resolved_error_type = error_type or derive_primary_error_type(errors)
        return RTLGenerationResult(
            status=RTLGenerationStatus.FAIL,
            module_name=hardware_spec.module_name,
            rtl=None,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            prompt_version=RTL_GENERATION_PROMPT_VERSION,
            attempts=attempts,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            raw_model_output=raw_model_output or None,
            error_type=resolved_error_type,
            error_message=errors[0] if errors else "RTL generation failed.",
        )


def extract_rtl_module(text: str) -> tuple[str | None, list[str]]:
    """Extract one credible module block from raw model output."""

    stripped = strip_single_markdown_fence(text.strip())
    candidate = stripped if stripped is not None else text.strip()
    if not candidate:
        return None, ["EMPTY_MODEL_RESPONSE: Model returned empty text."]

    module_start = candidate.find("module")
    if module_start == -1:
        return None, ["RTL_NOT_FOUND: No module declaration was found in model output."]

    module_pattern = re.compile(r"\bmodule\s+[A-Za-z_][A-Za-z0-9_$]*\b", re.MULTILINE)
    modules = list(module_pattern.finditer(candidate))
    if len(modules) == 0:
        return None, ["RTL_NOT_FOUND: No valid module declaration was found in model output."]
    if len(modules) > 1:
        return None, ["MULTIPLE_MODULES: Model output appears to contain multiple module declarations."]

    end_index = candidate.rfind("endmodule")
    if end_index == -1 or end_index < modules[0].start():
        return None, ["RTL_NOT_FOUND: No matching endmodule was found in model output."]

    extracted = candidate[modules[0].start() : end_index + len("endmodule")].strip()
    return extracted, []


def strip_single_markdown_fence(text: str) -> str | None:
    """Strip one outer Markdown code fence if the whole response is fenced."""

    lines = text.splitlines()
    if len(lines) < 3:
        return None
    if not lines[0].strip().startswith("```"):
        return None
    if lines[-1].strip() != "```":
        return None
    inner = "\n".join(lines[1:-1]).strip()
    return inner or None


def run_rtl_sanity_checks(hardware_spec: HardwareSpec, rtl_text: str) -> list[str]:
    """Run lightweight deterministic sanity checks on generated RTL text."""

    errors: list[str] = []

    module_pattern = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b", re.MULTILINE)
    module_matches = list(module_pattern.finditer(rtl_text))
    if len(module_matches) != 1:
        if len(module_matches) > 1:
            errors.append("MULTIPLE_MODULES: Generated RTL contains multiple module declarations.")
        else:
            errors.append("RTL_NOT_FOUND: Generated RTL does not contain a valid module declaration.")
        return errors

    declared_module_name = module_matches[0].group(1)
    if declared_module_name != hardware_spec.module_name:
        errors.append(
            f"MODULE_NAME_MISMATCH: Expected {hardware_spec.module_name} but model generated {declared_module_name}."
        )

    interface_errors = validate_module_interface(hardware_spec, rtl_text)
    errors.extend(interface_errors)

    forbidden_errors = detect_forbidden_constructs(rtl_text)
    errors.extend(forbidden_errors)

    semantic_errors = validate_basic_semantics(hardware_spec, rtl_text)
    errors.extend(semantic_errors)

    declaration_errors = validate_procedural_output_declarations(rtl_text)
    errors.extend(declaration_errors)

    return errors


def validate_module_interface(hardware_spec: HardwareSpec, rtl_text: str) -> list[str]:
    """Check that required port names appear in the module interface."""

    errors: list[str] = []
    header_match = re.search(
        r"\bmodule\s+[A-Za-z_][A-Za-z0-9_$]*\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;",
        rtl_text,
        re.DOTALL,
    )
    if header_match is None:
        return ["RTL_NOT_FOUND: Could not locate a complete module header with a port list."]

    port_list_text = header_match.group(1)
    for port in hardware_spec.ports:
        if not re.search(rf"\b{re.escape(port.name)}\b", port_list_text):
            errors.append(f"MISSING_REQUIRED_PORT: Required port '{port.name}' is missing from the module interface.")

    return errors


def detect_forbidden_constructs(rtl_text: str) -> list[str]:
    """Reject obvious simulation-only or unsafe constructs."""

    errors: list[str] = []
    for pattern, label in FORBIDDEN_CONSTRUCT_PATTERNS:
        if re.search(pattern, rtl_text, re.IGNORECASE | re.MULTILINE):
            errors.append(f"FORBIDDEN_SIMULATION_CONSTRUCT: Generated RTL contains forbidden construct '{label}'.")
    return errors


def validate_basic_semantics(hardware_spec: HardwareSpec, rtl_text: str) -> list[str]:
    """Perform simple design-type and reset-style checks without parsing full SystemVerilog."""

    errors: list[str] = []
    if hardware_spec.design_type == DesignType.COMBINATIONAL:
        if "always_ff" in rtl_text:
            errors.append("FORBIDDEN_SEQUENTIAL_CONSTRUCT: Combinational design should not use always_ff.")
    else:
        if "always_ff" not in rtl_text:
            errors.append("MISSING_SEQUENTIAL_CONSTRUCT: Sequential design should use always_ff.")

        if hardware_spec.clock is not None:
            expected_edge = "posedge" if hardware_spec.clock.edge.value == "positive" else "negedge"
            if expected_edge not in rtl_text or hardware_spec.clock.signal not in rtl_text:
                errors.append(
                    f"CLOCK_SEMANTICS_MISMATCH: Expected {expected_edge} {hardware_spec.clock.signal} in sequential RTL."
                )

        if hardware_spec.reset is not None:
            if hardware_spec.reset.type.value == "asynchronous":
                expected_reset_edge = (
                    "posedge" if hardware_spec.reset.polarity.value == "active_high" else "negedge"
                )
                if expected_reset_edge not in rtl_text or hardware_spec.reset.signal not in rtl_text:
                    errors.append(
                        "RESET_SEMANTICS_MISMATCH: Expected asynchronous reset sensitivity in always_ff header."
                    )
            else:
                if re.search(rf"always_ff\s*@\([^)]*{re.escape(hardware_spec.reset.signal)}", rtl_text):
                    errors.append(
                        "RESET_SEMANTICS_MISMATCH: Synchronous reset should not appear in the always_ff sensitivity list."
                    )

    return errors


def validate_procedural_output_declarations(rtl_text: str) -> list[str]:
    """Reject obvious procedurally assigned outputs declared without an explicit variable type."""

    errors: list[str] = []
    if "always_comb" not in rtl_text and "always_ff" not in rtl_text:
        return errors

    header_match = re.search(
        r"\bmodule\s+[A-Za-z_][A-Za-z0-9_$]*\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;",
        rtl_text,
        re.DOTALL,
    )
    if header_match is None:
        return errors

    port_list_text = header_match.group(1)
    for raw_port in port_list_text.split(","):
        port_decl = raw_port.strip()
        if not port_decl.startswith("output"):
            continue
        if "logic" in port_decl or "wire" in port_decl:
            continue
        if re.search(r"\boutput\b\s+(?:signed\s+)?(?:\[[^]]+\]\s+)?[A-Za-z_][A-Za-z0-9_$]*\b", port_decl):
            errors.append(
                "PROCEDURAL_OUTPUT_TYPE_MISMATCH: Procedurally assigned output ports should use an explicit variable type such as 'output logic'."
            )
            break

    return errors


def derive_primary_error_type(errors: list[str]) -> str:
    """Extract the primary structured error type from local errors."""

    if not errors:
        return "RTL_GENERATION_RETRY_EXHAUSTED"
    first = errors[0]
    prefix = first.split(":", 1)[0].strip()
    return prefix or "RTL_GENERATION_RETRY_EXHAUSTED"
