import json

REQUIREMENT_PARSER_PROMPT_VERSION = "1.2"
HARDWARE_INTENT_PROMPT_VERSION = "1.3"
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

    analysis_example = json.dumps(
        {
            "ready": False,
            "explicitly_specified": ["input_width", "output_width", "opcode_mapping"],
            "safely_inferred": ["select_width"],
            "missing_critical": ["signedness"],
            "ambiguous": ["signedness"],
            "clarification_questions": [
                {
                    "id": "signedness",
                    "field": "ports.signed",
                    "semantic_key": "signedness",
                    "question": "Should comparisons use signed or unsigned interpretation?",
                    "reason": "Ordered comparisons can change behavior under signed versus unsigned interpretation.",
                    "required": True,
                    "choices": ["signed", "unsigned"],
                    "default": None,
                }
            ],
            "assumptions": [],
        },
        separators=(",", ":"),
    )

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
- semantic_key: string
- question: string
- reason: string
- required: boolean
- choices: list[string]
- default: string or null

Valid JSON shape example:
{analysis_example}

Rules:
- If any critical hardware behavior is missing or ambiguous, set ready to false.
- When ready is false, include useful clarification_questions.
- Do not choose clock edge, reset polarity, widths, opcode mappings, count direction, or overflow behavior unless the user clearly specified them.
- Do not ask for facts that are already explicit in the requirement.
- Do not ask for values that are straightforwardly derivable from explicit structured facts or simple mathematics.
- Focus clarification on genuine design choices rather than re-asking widths, counts, or encodings that can be safely resolved.
- Distinguish truly missing information from derivable information.
- semantic_key must describe the unresolved fact or design choice using a generic hardware concept.
- Prefer generic semantic keys such as input_width, input_count, output_width, encoded_output_width, input_representation, signedness, reset_type, priority_direction, valid_output_presence, or latency when applicable.
- Do not encode an unrelated hardware family into semantic_key just to fit a known template.
- When the unresolved fact is the width of an encoded-index output, prefer semantic_key `encoded_output_width` instead of generic `output_width`.
- Apply family-specific ambiguity concepts only when the requirement is actually that family.
- If the hardware family is unknown or unsupported by the listed local policies, preserve generic uncertainty instead of coercing it into counter, ALU, mux, or FIFO templates.
- Do not emit counter_*, alu_*, mux_*, or fifo-like ambiguity ids unless the requirement is actually that compatible family.
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

    bit_select_example = json.dumps(
        {
            "type": "bit_select",
            "signal": {
                "type": "signal",
                "name": "data_in",
            },
            "index": 7,
        },
        separators=(",", ":"),
    )

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
- semantics: object or null
  - combinational: object or null
    - assignments: list of objects with:
      - target: output signal name
      - expression: typed semantic expression object
        - literal:
          - type: "literal"
          - value: non-negative integer
          - width: integer >= 1 or null
          - signed: boolean
        - signal:
          - type: "signal"
          - name: declared signal name
        - bit_select:
          - type: "bit_select"
          - signal: nested signal expression using the base declared vector identifier only
          - index: integer bit index within that vector
        - unary:
          - type: "unary"
          - op: "BIT_NOT" | "LOGICAL_NOT"
          - operand: nested expression
        - binary:
          - type: "binary"
          - op: "ADD" | "SUB" | "BIT_AND" | "BIT_OR" | "BIT_XOR" | "EQ" | "NE" | "LT" | "LE" | "GT" | "GE" | "SHIFT_LEFT" | "SHIFT_RIGHT" | "LOGICAL_AND" | "LOGICAL_OR"
          - left: nested expression
          - right: nested expression
        - select:
          - type: "select"
          - condition: nested expression
          - when_true: nested expression
          - when_false: nested expression
- semantic_constraints: object or null
  - conditionals: list of objects with:
    - target: output signal name
    - condition: typed semantic expression object that evaluates to 1 bit
    - expected_expression: typed semantic expression object using the same supported expression node forms as semantics.combinational.assignments
  - legacy `control_signal` / `control_value` pairs remain accepted for simple saved specs, but new output should prefer `condition`
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
- When a combinational design's output logic is clear and expressible with the supported semantic nodes/operators, populate semantics.combinational.assignments.
- Prefer structured semantics for common combinational behavior such as:
  - comparators: eq = (a == b), gt = (a > b), lt = (a < b)
  - muxes: y = select ? b : a
  - simple arithmetic/logic datapaths: sum = a + b, y = (a & b) | c
- SignalExpr.name must contain only the base signal identifier.
- Never encode vector indexing such as `data_in[7]` inside SignalExpr.name.
- Use BitSelectExpr for vector bit access.
- Example BitSelectExpr:
  - `{bit_select_example}`
- When the requirement gives explicit conditional branch meaning such as "when sel is 0 -> A" and "when sel is 1 -> B", emit BOTH:
  - the semantic AST
  - structured semantic_constraints.conditionals entries preserving those branch mappings
- For natural-language statements like "when sel is 0 -> A, when sel is 1 -> B", a SelectExpr with condition=sel must encode when_true=B and when_false=A.
- For a one-bit SelectExpr condition, verify branch direction before returning JSON:
  - condition=sel
  - when_true corresponds to sel=1
  - when_false corresponds to sel=0
- Example:
  - "When sel is 0, y = a + b. When sel is 1, y = a XOR b."
  - SelectExpr: condition=sel, when_true=BIT_XOR(a,b), when_false=ADD(a,b)
  - semantic_constraints.conditionals must preserve:
    - condition=LOGICAL_NOT(sel) -> ADD(a,b)
    - condition=sel -> BIT_XOR(a,b)
- For priority-style or precedence-driven combinational behavior, prefer ordinary nested SelectExpr composition over inventing unrelated arithmetic operators.
- Use nested SelectExpr conditions to represent ordered precedence such as checking one asserted bit before another.
- Do not fabricate operators like SUB merely to connect conditional branches.
- Structured semantics, structured constraints, and behavior prose must agree with resolved clarification answers.
- If semantics cannot be represented safely with the supported nodes/operators, set semantics to null instead of inventing unsupported semantics.
- Do not emit semantic_constraints without corresponding structured semantics.
- If semantic_constraints are present, emit compatible semantics.combinational.assignments that match them.
- If no valid structured semantics can be represented, omit semantic_constraints as well.
- Do not place sequential or stateful behavior inside semantics.combinational.

Return one valid JSON object.

User requirement:
{requirement}
"""


def build_hardware_intent_prompt(requirement: str) -> str:
    """Build the primary prompt for converting a clarified requirement into high-level HardwareIntent JSON."""

    case_select_example = json.dumps(
        {
            "type": "case_select",
            "selector": {"type": "signal", "name": "op"},
            "cases": [
                {
                    "value": 0,
                    "expression": {
                        "type": "binary",
                        "op": "ADD",
                        "left": {"type": "signal", "name": "a"},
                        "right": {"type": "signal", "name": "b"},
                    },
                },
                {
                    "value": 1,
                    "expression": {
                        "type": "binary",
                        "op": "SUB",
                        "left": {"type": "signal", "name": "a"},
                        "right": {"type": "signal", "name": "b"},
                    },
                },
                {
                    "value": 2,
                    "expression": {
                        "type": "binary",
                        "op": "BIT_XOR",
                        "left": {"type": "signal", "name": "a"},
                        "right": {"type": "signal", "name": "b"},
                    },
                },
                {
                    "value": 3,
                    "expression": {
                        "type": "conditional",
                        "condition": {
                            "type": "binary",
                            "op": "GT",
                            "left": {"type": "signal", "name": "a"},
                            "right": {"type": "signal", "name": "b"},
                        },
                        "when_true": {"type": "signal", "name": "a"},
                        "when_false": {"type": "signal", "name": "b"},
                    },
                },
            ],
            "default_expression": {"type": "literal", "value": 0, "width": 8, "signed": False},
        },
        separators=(",", ":"),
    )
    priority_select_example = json.dumps(
        {
            "type": "priority_select",
            "source_signal": "data_in",
            "direction": "HIGHEST_INDEX_FIRST",
            "output_mode": "INDEX",
            "default_value": 0,
        },
        separators=(",", ":"),
    )
    zero_flag_example = json.dumps(
        {
            "target": "zero",
            "expression": {
                "type": "binary",
                "op": "EQ",
                "left": {"type": "signal", "name": "y"},
                "right": {"type": "literal", "value": 0, "width": 8, "signed": False},
            },
        },
        separators=(",", ":"),
    )
    carry_example = json.dumps(
        {
            "type": "bit_select",
            "signal": {
                "type": "binary",
                "op": "ADD",
                "left": {
                    "type": "extend",
                    "operand": {"type": "signal", "name": "a"},
                    "target_width": 9,
                    "mode": "ZERO_EXTEND",
                },
                "right": {
                    "type": "extend",
                    "operand": {"type": "signal", "name": "b"},
                    "target_width": 9,
                    "mode": "ZERO_EXTEND",
                },
            },
            "index": 8,
        },
        separators=(",", ":"),
    )
    max_example = json.dumps(
        {
            "type": "conditional",
            "condition": {
                "type": "binary",
                "op": "GT",
                "left": {"type": "signal", "name": "a"},
                "right": {"type": "signal", "name": "b"},
            },
            "when_true": {"type": "signal", "name": "a"},
            "when_false": {"type": "signal", "name": "b"},
        },
        separators=(",", ":"),
    )

    return f"""ROLE
Convert the FINAL CLARIFIED HARDWARE REQUIREMENT into exactly one valid HardwareIntent JSON object.

HARD RULES
- Return JSON only.
- No Markdown.
- No code fences.
- No commentary before or after JSON.
- Use double-quoted JSON keys and strings.
- Return the complete HardwareIntent object every time.
- Do not generate Verilog or SystemVerilog.
- Do not invent unsupported fields, primitives, or operators.
- Use concrete JSON numbers only. Do not emit arithmetic strings like "2**8".
- Focus authoritative correctness on module_name, ports, and combinational_intent.
- behavior, tags, and notes are descriptive metadata only. Keep them concise or omit them.
- Any RESOLVED REQUIREMENT FACTS section is authoritative: preserve every target, condition, true behavior, and otherwise behavior exactly.

AUTHORITATIVE COMBINATIONAL SHAPE
- schema_version: "1.0"
- module_name
- design_type: "combinational"
- ports
- combinational_intent.assignments

REQUIRED PORT CONTRACT
- EVERY port object MUST contain:
  - "name"
  - "width"
  - "direction": "input" | "output" | "inout"
  - "signed": true | false
- Do not omit direction on any port.
- Example input port: {{"name":"a","width":8,"direction":"input","signed":false}}
- Example output port: {{"name":"y","width":8,"direction":"output","signed":false}}

SUPPORTED EXPRESSION TYPES
- literal
- signal
- unary
- binary
- conditional
- case_select
- priority_select
- bit_select
- extend

SUPPORTED OPERATORS
- unary: NONZERO, BIT_NOT, LOGICAL_NOT
- binary: ADD, SUB, BIT_AND, BIT_OR, BIT_XOR, EQ, NE, LT, LE, GT, GE, SHIFT_LEFT, SHIFT_RIGHT, LOGICAL_AND, LOGICAL_OR
- extend modes: ZERO_EXTEND, SIGN_EXTEND
- priority directions: LOWEST_INDEX_FIRST, HIGHEST_INDEX_FIRST

PRIMITIVE SELECTION GUIDE
- CONDITIONAL: one binary if/else choice.
- CASE_SELECT: selector/opcode/mode dispatch where explicit selector values choose different expressions.
- PRIORITY_SELECT: ONLY for choosing which source vector bit wins by priority.
- NEVER use PRIORITY_SELECT as switch/case or opcode dispatch.

WIDTH RULES
- Respect declared port widths.
- Comparison expressions produce 1-bit results.
- CONDITIONAL and CASE_SELECT result branches must resolve to compatible widths.
- For an N-bit target assigned N-bit ADD or SUB operands, use ordinary fixed-width ADD or SUB unless the requirement explicitly makes the result wider.
- Do not extend ordinary fixed-width arithmetic merely because mathematical overflow is possible.
- Use explicit extend only when width growth is required by the result itself, such as a wider output, explicit extension, or a separate widened expression used to derive carry/overflow information.
- If a separate output needs a widened arithmetic bit, keep the main result fixed-width and build a separate extended expression for that derived output.

CONDITIONAL OUTPUT RULES
- If output X is E when condition C and D otherwise, assign X a CONDITIONAL with condition=C, when_true=E, and when_false=D.
- Preserve all three parts of an explicit conditional output rule. Do not replace it with EQ(E,D), NONZERO(E), only E, or only D.
- EQ(A,B) produces the 1-bit result of comparing A and B; it does not assign A or extract A's value.
- BIT_SELECT(expression,index) already produces the selected bit value. Use it directly, or wrap it in CONDITIONAL when the requirement gates that value.

ZERO AND STATUS RULES
- NONZERO(x) means x != 0.
- A zero flag must use EQ(x, 0), not NONZERO(x).
- A derived output may reference another output if the dependency is acyclic.
- Do not create cyclic output dependencies.

NO INVENTED SEMANTICS
- Do not invent operators such as CARRY, MAX, MUX, ALU_OP, ZERO_FLAG, or COMPARE_GT.
- Those words may appear only as signal names if the requirement explicitly declares them.
- Compose behavior from supported generic primitives.

CANONICAL MINI-EXAMPLES
- CASE_SELECT opcode dispatch:
  {case_select_example}
- PRIORITY_SELECT vector priority:
  {priority_select_example}
- zero flag from y:
  {zero_flag_example}
- unsigned carry-out for 8-bit add:
  {carry_example}
- The carry example is a separate widened expression for a derived bit; do not widen an ordinary fixed-width result assignment.
- max(a,b):
  {max_example}

OUTPUT CONTRACT
- Return exactly one complete HardwareIntent JSON object.
- If a behavior cannot be represented with the supported schema, do not improvise another shape.
- Keep descriptive metadata brief.
- Before returning JSON verify:
  - every port has direction
  - every referenced signal exists
  - every assignment target is an output
  - only supported expression types and operators are used

FINAL CLARIFIED HARDWARE REQUIREMENT
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
Do not use comments or Python syntax.
Arrays contain values only, never key:value pairs.
Objects use {{}} and lists use [].
Do not invent missing critical hardware details.
Do not ask for facts already explicit in the requirement.
Do not ask for widths, counts, or encodings that are straightforwardly derivable from explicit requirement facts.
Focus repaired clarification on genuine unresolved design choices.

Required analysis JSON fields:
- ready
- explicitly_specified
- safely_inferred
- missing_critical
- ambiguous
- clarification_questions
- assumptions

Each clarification question must still carry:
- id
- field
- semantic_key
- question
- reason
- required
- choices
- default

Required analysis JSON shape example:
{{"ready":false,"explicitly_specified":["input_width"],"safely_inferred":[],"missing_critical":["signedness"],"ambiguous":["signedness"],"clarification_questions":[{{"id":"signedness","field":"ports.signed","semantic_key":"signedness","question":"Should comparisons use signed or unsigned interpretation?","reason":"Ordered comparisons can change behavior under signed versus unsigned interpretation.","required":true,"choices":["signed","unsigned"],"default":null}}],"assumptions":[]}}

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
    semantic_constraint_guidance = ""
    if any("SEMANTIC_CONSTRAINT_MISMATCH" in error for error in validation_errors):
        semantic_constraint_guidance = """
- If a validation error reports SEMANTIC_CONSTRAINT_MISMATCH:
  - the structured conditional constraint is preserving the explicit requirement meaning
  - make the semantic AST agree with that structured conditional constraint
  - for a one-bit SelectExpr, sel=1 maps to when_true and sel=0 maps to when_false
  - do not try to fix this only by rewording behavior prose
"""
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
- If combinational semantics are clear and safely representable, prefer the typed semantics section instead of only prose rules.
- If the requirement defines explicit conditional branch direction, ensure SelectExpr branch mapping matches it exactly.
- For a one-bit SelectExpr condition, re-check that when_true is the sel=1 branch and when_false is the sel=0 branch before returning corrected JSON.
- If the requirement defines explicit conditional branch meaning, include matching semantic_constraints.conditionals entries and make the semantic AST agree with them.
- If a validation error reports SEMANTIC_CONSTRAINT_MISMATCH, fix the semantic AST and semantic_constraints structurally rather than rephrasing behavior prose.
- SignalExpr.name must remain the base identifier only; vector indexing must use BitSelectExpr.
- Priority-style conditional semantics should be represented with nested SelectExpr composition and typed BitSelectExpr conditions when needed.
- Do not use unrelated arithmetic operators to emulate conditional precedence.
- Ensure structured semantics, semantic_constraints, and behavior prose all agree with resolved clarification answers.
- Do not emit semantic_constraints without corresponding structured semantics.
- If semantic_constraints are present, either:
  - emit valid semantics.combinational.assignments matching those constraints, or
  - omit semantic_constraints if no structured semantics can be represented safely.
{semantic_constraint_guidance}

Original requirement:
{requirement}

Previous invalid output:
{previous_output}

Validation errors:
{joined_errors}
"""


def build_hardware_intent_json_repair_prompt(requirement: str, previous_output: str, json_error: str) -> str:
    """Build a focused syntax-repair prompt for malformed HardwareIntent JSON."""

    conditional_example = json.dumps(
        {
            "type": "conditional",
            "condition": {"type": "signal", "name": "enable"},
            "when_true": {"type": "signal", "name": "a"},
            "when_false": {"type": "signal", "name": "b"},
        },
        separators=(",", ":"),
    )
    bit_select_example = json.dumps(
        {
            "type": "bit_select",
            "signal": {"type": "signal", "name": "data"},
            "index": 0,
        },
        separators=(",", ":"),
    )
    extend_example = json.dumps(
        {
            "type": "extend",
            "operand": {"type": "signal", "name": "data"},
            "target_width": 9,
            "mode": "ZERO_EXTEND",
        },
        separators=(",", ":"),
    )

    return f"""Repair the malformed HardwareIntent JSON syntax while preserving its intended hardware semantics.

HARD RULES
- Return JSON only: no Markdown, code fences, comments, or prose.
- Return one COMPLETE HardwareIntent object, not a fragment, patch, or diff.
- Preserve valid ports, assignments, primitive choices, and clarified behavior where possible.
- Preserve every obligation in RESOLVED REQUIREMENT FACTS; syntax repair must not drop a condition or branch.
- Rebuild malformed nesting with matching {{}} objects and [] arrays.
- Separate every object field and array element with commas.
- Keep every nested expression field inside its parent expression object.

REQUIRED TOP-LEVEL CONTRACT
- schema_version
- module_name
- design_type
- ports; every port has name, width, direction, and signed
- combinational_intent.assignments; every assignment has target and expression

EXACT NESTED SHAPES
- conditional: {conditional_example}
- bit_select: {bit_select_example}
- extend: {extend_example}

SEMANTIC PRESERVATION CHECK
- Keep N-bit ADD/SUB assigned to an N-bit target fixed-width unless the requirement explicitly widens that result.
- Use extend only for explicit width growth or a separate widened expression used to derive carry/overflow information.
- Preserve "X is E when C, otherwise D" as CONDITIONAL(condition=C, when_true=E, when_false=D).
- BIT_SELECT directly produces a bit value; EQ produces a boolean comparison result.

FINAL CLARIFIED REQUIREMENT
{requirement}

PREVIOUS MALFORMED RESPONSE
{previous_output}

JSON PARSER ERROR
{json_error}
"""


def build_hardware_intent_repair_prompt(requirement: str, previous_output: str, validation_errors: list[str]) -> str:
    """Build the corrective prompt used after HardwareIntent schema/compiler failure."""

    joined_errors = "\n".join(f"- {error}" for error in validation_errors) or "- Unknown validation failure"
    targeted_hints = build_hardware_intent_repair_hints(validation_errors)
    return f"""You previously attempted to convert a hardware requirement into HardwareIntent JSON, but the result was invalid.

Return corrected JSON only.
No Markdown.
No code fences.
No prose.
Return the COMPLETE corrected HardwareIntent object, not a patch or diff.
Preserve valid ports, assignments, and correct primitive choices where possible.
Repair only the reported syntax/schema/semantic violations, but still return the complete object.
Keep the clarified hardware meaning intact.
Preserve every obligation in RESOLVED REQUIREMENT FACTS, including its condition and both branches.
Do not invent unsupported fields, primitives, or operators.
behavior, tags, and notes are optional descriptive metadata only.
Do not spend repair budget on verbose metadata.

Authoritative combinational requirements:
- schema_version
- module_name
- design_type
- ports
- combinational_intent.assignments

Supported expression types:
- literal
- signal
- unary
- binary
- conditional
- case_select
- priority_select
- bit_select
- extend

Important semantic rules:
- CASE_SELECT is for selector-value dispatch.
- PRIORITY_SELECT is only for source-bit priority over a vector.
- NONZERO(x) means x != 0.
- A zero flag must use EQ(x,0).
- Carry-out must use extend + ADD + bit_select. Do not invent a CARRY operator.
- For an N-bit target receiving N-bit ADD or SUB operands, keep arithmetic fixed-width unless the requirement explicitly requires a wider result.
- Use extend for explicit width growth or a separate widened expression used to derive carry/overflow information, not ordinary fixed-width result branches.
- CONDITIONAL and CASE_SELECT branches must resolve to a width compatible with the assignment target.
- If output X is E when condition C and D otherwise, use CONDITIONAL(condition=C, when_true=E, when_false=D); preserve all three parts.
- EQ(A,B) produces a boolean comparison result. BIT_SELECT(expr,k) directly produces the selected bit value.
- If a selected bit is conditionally visible, wrap BIT_SELECT in CONDITIONAL rather than comparing the bit with EQ.
- Derived outputs may reference another output only when acyclic.
{targeted_hints}

Final clarified requirement:
{requirement}

Previous invalid output:
{previous_output}

Validation/compiler errors:
{joined_errors}
"""


def build_hardware_intent_repair_hints(validation_errors: list[str]) -> str:
    """Return concise deterministic HardwareIntent repair hints for common DSL misuse patterns."""

    joined = "\n".join(validation_errors).upper()
    hints: list[str] = []

    if "PRIORITY_SELECT" in joined and ("CASE" in joined or "SELECTOR" in joined or "OPCODE" in joined):
        hints.append("- PRIORITY_SELECT is only for source-bit priority. Use CASE_SELECT for selector-value dispatch.")
    if "CARRY" in joined:
        hints.append("- Do not invent a CARRY operator. Represent carry using extend + ADD + bit_select.")
    if "NONZERO" in joined and "ZERO" in joined:
        hints.append("- NONZERO(x) means x != 0. A zero flag must use EQ(x,0).")
    if "PORTS" in joined and "DIRECTION" in joined and "FIELD REQUIRED" in joined:
        hints.append(
            "- Every port requires direction. Use 'input' for requirement inputs and 'output' for requirement outputs, "
            "and return the complete corrected HardwareIntent with direction present on every port."
        )
    if "WIDTH" in joined or "BRANCH" in joined:
        hints.append(
            "- CASE_SELECT and CONDITIONAL branches must match the assignment target width. Keep fixed-width ADD/SUB "
            "fixed-width; use extend only when the requirement or a separate derived widened expression needs growth."
        )
    if "WHEN_TRUE" in joined or "WHEN_FALSE" in joined or "CONDITION" in joined:
        hints.append(
            "- Keep condition, when_true, and when_false inside the same CONDITIONAL expression object and preserve "
            "the requirement's complete condition/true/false behavior."
        )
    if "UNSUPPORTED_HARDWARE_INTENT" in joined:
        hints.append("- Use only the supported expression types and operators listed above. Do not invent a new primitive name.")

    if not hints:
        return ""
    return "\nTargeted correction hints:\n" + "\n".join(hints)
