REQUIREMENT_PARSER_PROMPT_VERSION = "1.0"
REQUIREMENT_ANALYSIS_PROMPT_VERSION = "1.0"

CRITICAL_AMBIGUITY_POLICY: dict[str, list[str]] = {
    "sequential": [
        "state width when applicable",
        "clock edge",
        "reset existence and semantics",
        "reset type",
        "reset polarity",
        "enable behavior when it changes functionality",
        "counter direction",
        "overflow behavior",
        "initial/reset state",
        "state-transition behavior for FSMs",
    ],
    "alu_arithmetic": [
        "operand width",
        "signed vs unsigned arithmetic behavior",
        "supported operations",
        "opcode mapping for opcode-controlled operations",
        "result width",
        "carry/overflow semantics when requested",
    ],
    "mux_like": [
        "number of inputs",
        "data width",
        "select width or mapping",
        "output width",
    ],
    "fifo_like": [
        "data width",
        "depth",
        "clock/reset semantics",
        "read behavior while empty",
        "write behavior while full",
    ],
}

ALLOWED_NONCRITICAL_ASSUMPTIONS: list[str] = [
    "generated module naming convention",
    "descriptive tags",
    "descriptive prose",
]


def build_requirement_analysis_prompt(requirement: str) -> str:
    """Build the primary prompt for structured ambiguity analysis."""

    return f"""You are a hardware requirement ambiguity analyzer.

Task:
Analyze the user's natural-language hardware requirement and determine whether it contains enough information to safely generate a final HardwareSpec without inventing critical hardware behavior.

Return JSON only.
Do not return Markdown.
Do not wrap the JSON in triple backticks.
Do not generate HardwareSpec JSON.
Do not generate SystemVerilog.
Do not silently resolve missing critical behavior.

Critical hardware details include, when relevant:
- sequential designs:
  - {", ".join(CRITICAL_AMBIGUITY_POLICY["sequential"])}
- ALUs or arithmetic modules:
  - {", ".join(CRITICAL_AMBIGUITY_POLICY["alu_arithmetic"])}
- mux-like combinational designs:
  - {", ".join(CRITICAL_AMBIGUITY_POLICY["mux_like"])}
- FIFO-like designs:
  - {", ".join(CRITICAL_AMBIGUITY_POLICY["fifo_like"])}

Harmless assumptions that may be safely inferred include:
- {ALLOWED_NONCRITICAL_ASSUMPTIONS[0]}
- {ALLOWED_NONCRITICAL_ASSUMPTIONS[1]}
- {ALLOWED_NONCRITICAL_ASSUMPTIONS[2]}

Return one JSON object with exactly these fields:
- ready: boolean
- explicitly_specified: list[string]
- safely_inferred: list[string]
- missing_critical: list[string]
- ambiguous: list[string]
- clarification_questions: list[object]
- assumptions: list[string]

Each clarification question object must contain:
- id: string
- field: string
- question: string
- reason: string
- required: boolean
- choices: list[string]
- default: string or null

Rules:
- If any critical hardware behavior is missing or ambiguous, set ready to false.
- When ready is false, include useful clarification_questions.
- Do not choose clock edge, reset polarity, widths, opcode mappings, count direction, or overflow behavior unless the user clearly specified them.
- Prefer these canonical ambiguity ids when applicable:
  - counter_width
  - clock_edge
  - reset_presence
  - reset_type
  - reset_polarity
  - count_direction
  - overflow_behavior
  - enable_behavior
  - reset_value
  - alu_width
  - alu_signedness
  - alu_operations
  - opcode_mapping
  - result_width
  - carry_behavior
  - mux_input_count
  - mux_data_width
  - mux_select_mapping
- A vague prompt such as "Create a counter." is not ready.
- A vague prompt such as "Create an ALU." is not ready.

User requirement:
{requirement}
"""


def build_requirement_parser_prompt(requirement: str) -> str:
    """Build the primary prompt for converting a requirement into HardwareSpec JSON."""

    return f"""You are a hardware specification generator.

Task:
Convert the user's natural-language hardware requirement into a JSON object that matches the HardwareSpec schema exactly.

Rules:
- Return JSON only.
- Do not return Markdown.
- Do not wrap the JSON in triple backticks.
- Do not generate SystemVerilog.
- Do not include explanatory prose outside the JSON.
- Do not invent unsupported top-level fields.
- Set schema_version to "1.0".
- Preserve explicit user requirements exactly when possible.
- Do not silently invent critical hardware behavior.
- If noncritical details are missing, record them in behavior.assumptions.
- If a reset is explicitly requested, include reset details only if they are stated or clearly labeled as assumptions.
- Use lowercase enum values exactly as listed below.

Supported top-level schema:
- schema_version: string
- module_name: string
- design_type: "combinational" | "sequential"
- description: string | null
- parameters: list of objects with:
  - name: string
  - default: int | string | bool
  - description: string | null
- ports: list of objects with:
  - name: string
  - direction: "input" | "output" | "inout"
  - width: integer >= 1
  - signed: boolean
  - role: "data" | "clock" | "reset" | "control" | "status" | "other"
  - description: string | null
- clock: object or null
  - signal: string
  - edge: "positive" | "negative"
  - frequency_hz: positive number | null
- reset: object or null
  - signal: string
  - type: "synchronous" | "asynchronous"
  - polarity: "active_high" | "active_low"
  - priority: string | null
  - reset_values: object mapping signal names to integers or strings
- behavior: object
  - description: string
  - operations: list of strings
  - rules: list of strings
  - assumptions: list of strings
- tags: list of strings

Validation-sensitive guidance:
- Sequential designs require a clock.
- Combinational designs should set clock to null and reset to null.
- Clock and reset signals must appear in ports.
- Clock ports should be role "clock" and width 1.
- Reset ports should be role "reset" and width 1.
- Use simple identifier names only.

Return one valid JSON object.

User requirement:
{requirement}
"""


def build_requirement_analysis_repair_prompt(requirement: str, previous_output: str, validation_errors: list[str]) -> str:
    """Build the corrective prompt used after ambiguity-analysis JSON/schema failure."""

    joined_errors = "\n".join(f"- {error}" for error in validation_errors) or "- Unknown validation failure"
    return f"""You previously analyzed a hardware requirement for ambiguity, but your result was invalid.

Return corrected JSON only.
Do not return Markdown.
Do not wrap the JSON in triple backticks.
Do not generate HardwareSpec JSON.
Do not invent missing critical hardware details.

Required analysis JSON fields:
- ready
- explicitly_specified
- safely_inferred
- missing_critical
- ambiguous
- clarification_questions
- assumptions

Original requirement:
{requirement}

Previous invalid output:
{previous_output}

Validation errors:
{joined_errors}
"""


def build_requirement_repair_prompt(requirement: str, previous_output: str, validation_errors: list[str]) -> str:
    """Build the corrective prompt used after JSON or schema validation failure."""

    joined_errors = "\n".join(f"- {error}" for error in validation_errors) or "- Unknown validation failure"
    return f"""You previously attempted to convert a hardware requirement into HardwareSpec JSON, but the result was invalid.

Return corrected JSON only.

Rules:
- Return JSON only.
- Do not return Markdown.
- Do not wrap the JSON in triple backticks.
- Correct only the JSON so it conforms to the HardwareSpec schema.
- Keep schema_version as "1.0".
- Do not change the user's intent.
- Do not invent unsupported fields.
- If information is missing but not critical, place the uncertainty in behavior.assumptions.

Original requirement:
{requirement}

Previous invalid output:
{previous_output}

Validation errors:
{joined_errors}
"""
