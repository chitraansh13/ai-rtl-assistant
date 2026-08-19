from rtl_assistant.models.hardware_spec import HardwareSpec

VERIFICATION_PLAN_PROMPT_VERSION = "1.1"


def build_verification_plan_prompt(hardware_spec: HardwareSpec) -> str:
    """Build the primary prompt for structured verification-plan generation."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    return f"""You are a careful hardware verification planner.

Task:
Generate a structured verification plan in JSON only for the validated HardwareSpec below.

Rules:
- Return JSON only.
- Do not return Markdown.
- Do not wrap JSON in triple backticks.
- Do not include explanations outside the JSON object.
- Do not generate SystemVerilog.
- Do not generate a testbench.
- Do not invent external ports.
- Do not change the HardwareSpec.
- Tests must be derived from the HardwareSpec behavior.
- Every critical behavior should have at least one explicit test case.
- Include meaningful edge or boundary cases when they matter.
- Avoid redundant tests that check the exact same behavior.
- HardwareSpec is the source of truth.
- Prioritize correct test intent and legal hardware stimulus.
- Provide expected outputs when possible, but expected values may be deterministically canonicalized from HardwareSpec semantics.
- If the HardwareSpec uses unsigned ports or signed=false, do not reinterpret the design as signed.
- Do not describe ordinary positive bit patterns as negative numbers for an unsigned design.
- For fixed-width unsigned arithmetic, expected results must respect the output width and natural wrap/truncation behavior when implied by the HardwareSpec.
- For unsigned subtraction, calculate the fixed-width modulo result carefully.
- Before emitting a test case, internally verify that numeric examples are mathematically correct for ADD, carry, SUB, AND, OR, and zero behavior.
- If expected arithmetic behavior is uncertain, choose a simpler correct vector instead of inventing one.

Schema expectations:
- Top-level fields: schema_version, module_name, design_type, strategy, test_cases, coverage_targets, assumptions, notes
- test_cases is a list of structured test cases
- Each test case must include: id, name, category, description, setup, stimulus, expected, covers, priority
- Use lowercase snake_case for each test case id
- Use priority values 1, 2, or 3 only
- category MUST be one of: BASIC, FUNCTIONAL, RESET, CONTROL, EDGE_CASE, BOUNDARY, STATE_TRANSITION, ARITHMETIC, INVALID_OR_GUARDED, OTHER
- setup, stimulus, expected, and covers MUST be JSON arrays of strings
- coverage_targets, assumptions, and notes MUST be JSON arrays of strings
- Do not use JSON objects for setup, stimulus, expected, covers, coverage_targets, assumptions, or notes
- expected must describe observable outcomes
- covers must identify the behavior or rule being validated

Small shape example:
{{
  "test_cases": [
    {{
      "id": "mux_select_zero",
      "setup": ["set select=0"],
      "stimulus": ["drive a=1", "drive b=0"],
      "expected": ["y equals a", "y=1"],
      "covers": ["select=0 mapping"]
    }}
  ],
  "coverage_targets": ["all specified routing paths"],
  "assumptions": ["stimulus is applied before the relevant observation point"],
  "notes": ["keep the plan concise and non-redundant"]
}}

Planning guidance:
- For mux or simple combinational logic: cover every specified select or control mapping and representative data behavior
- For ALU or arithmetic logic: cover every listed operation, opcode mapping, zero behavior, carry behavior if specified, and useful arithmetic boundary cases
- If a carry output exists for ADD behavior, include at least one test where carry is expected to assert
- Bitwise AND/OR tests should preferably use category FUNCTIONAL
- Test names and descriptions must accurately describe the vectors they contain
- Do not call `15 + 1` "two maximum values" or use similarly inaccurate wording
- Focus on choosing meaningful vectors and legal state/setup conditions rather than acting as the final arithmetic oracle
- For counters or sequential logic: cover reset, clocked state updates, enable or hold behavior, boundary wrap behavior, and reset priority if represented
- For sequential designs, do not directly assign internal state or output state
- State must be reached through legal reset, control inputs, and active clock transitions
- Every verification test should be independently reproducible
- Each test must either establish its own required state through legal reset/input/clock transitions or state a clear legal precondition
- If a test needs a counter state such as count=15, describe reaching it through legal clocked behavior rather than driving count directly
- Bad sequential setup example: `count=15`
- Better sequential setup examples: `apply 15 rising edges to reach count=15` or `precondition: count has legally reached 15`
- Prefer self-contained state preparation when practical rather than depending on a previous test having already run
- Positive-edge designs should reference a rising edge, positive edge, or next active edge for state changes
- Negative-edge designs should reference a falling edge, negative edge, or next active edge for state changes
- Do not represent clocking by merely setting the clock level such as `clk=1` or `clk high`
- Prefer logical event wording such as `apply one rising edge` or `apply one falling edge`
- For synchronous reset, describe asserting reset and then applying the active clock edge before expecting the reset value
- Prefer the smallest sequence that proves the behavior; avoid unnecessary long runs such as 100 or 1000 cycles unless the HardwareSpec requires them
- For hold behavior, prefer proving a nonzero state first and then showing it remains unchanged when the enable/control condition disables updates
- For wraparound behavior, prefer establishing the boundary state legally and then applying one additional active edge to prove the wrap transition
- For future FIFO-like designs: keep the plan focused on specified functional behavior, guarded cases, and state transitions

Width examples:
- For a 4-bit unsigned operand, valid values are 0..15 and the modulus is 16
- Example reasoning only: 15 + 1 -> result 0, carry 1
- Example reasoning only: 3 - 5 -> result 14 for fixed-width unsigned wraparound
- Example reasoning only: 10 AND 6 -> 2
- Example reasoning only: 5 OR 3 -> 7

Assumptions:
- Assumptions may only come from HardwareSpec assumptions or harmless verification-method assumptions
- Do not invent hardware behavior in assumptions

Validated HardwareSpec JSON:
{spec_json}
"""


def build_verification_plan_repair_prompt(
    hardware_spec: HardwareSpec,
    previous_output: str,
    errors: list[str],
) -> str:
    """Build the repair prompt for plan-structure or sanity failures."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    joined_errors = "\n".join(f"- {error}" for error in errors) or "- Unknown verification-plan generation failure"
    return f"""You previously generated an invalid verification plan.

Return repaired JSON only.
- No Markdown.
- No explanations.
- Preserve the intended tests where possible.
- Fix only the verification plan.
- Directly correct every listed validation error.
- Fix the semantic cause of each error, not just the wording.
- Do not merely rename or rephrase tests if the underlying problem remains.
- Preserve valid parts of the previous plan where possible.
- Maintain HardwareSpec semantics exactly.
- Do not introduce new illegal output assignments.
- Return a complete corrected JSON object, not a partial patch.
- Do not invent new hardware behavior.
- Do not generate SystemVerilog or testbench code.
- Preserve valid test intent and vector choice where possible, but fix every listed error at the semantic level.
- If expected values are machine-computable from the HardwareSpec, align them with the deterministic semantics instead of preserving an incorrect arithmetic or logic result.

If an error reports UNESTABLISHED_PRECONDITION:
- Do not directly assign the internal/output state.
- Either establish the required state through legal inputs, reset behavior, and active clock transitions, or state a clear legal precondition describing how that state has already been reached.
- The repaired test must be independently reproducible and must not depend on a previous test case.
- Acceptable conceptual repair:
  - setup: reset to known state, deassert reset, enable, apply enough active edges to legally reach the boundary
  - stimulus: apply one additional active edge
  - expected: wrapped state
- Also acceptable:
  - setup: precondition: state has legally reached the required boundary through valid transitions

Validated HardwareSpec JSON:
{spec_json}

Previous invalid model output:
{previous_output}

Errors to fix:
{joined_errors}
"""
