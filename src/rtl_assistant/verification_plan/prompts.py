import json

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.hardware_spec import PortDirection
from rtl_assistant.semantics.capabilities import derive_combinational_semantic_capabilities
from rtl_assistant.verification_plan.semantics import derive_supported_behaviors

VERIFICATION_PLAN_PROMPT_VERSION = "2.3"


def build_verification_plan_prompt(hardware_spec: HardwareSpec) -> str:
    """Build the primary prompt for structured verification-intent generation."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    allowed_input_hint_names = [
        port.name
        for port in hardware_spec.ports
        if port.direction == PortDirection.INPUT
        and (hardware_spec.clock is None or port.name != hardware_spec.clock.signal)
    ]
    grounded_behaviors = sorted(derive_supported_behaviors(hardware_spec))
    semantic_features = [feature.model_dump(mode="json") for feature in hardware_spec.semantic_features]
    semantic_capabilities = (
        sorted(derive_combinational_semantic_capabilities(hardware_spec.semantics.combinational))
        if hardware_spec.semantics is not None and hardware_spec.semantics.combinational is not None
        else []
    )
    allowed_input_hint_text = ", ".join(allowed_input_hint_names) if allowed_input_hint_names else "(none)"
    grounded_behavior_text = ", ".join(grounded_behaviors) if grounded_behaviors else "(none)"
    semantic_feature_text = json.dumps(semantic_features, indent=2) if semantic_features else "[]"
    semantic_capability_text = ", ".join(semantic_capabilities) if semantic_capabilities else "(none)"
    return f"""You are a careful hardware verification intent planner.

Task:
Generate a structured VerificationIntentPlan in JSON only for the validated HardwareSpec below.

Rules:
- Always return exactly one complete VerificationIntentPlan JSON object.
- Return JSON only.
- Do not return Markdown.
- Do not wrap JSON in triple backticks.
- Do not include explanations outside the JSON object.
- Do not generate SystemVerilog.
- Do not generate a testbench.
- Do not invent external ports.
- Do not change the HardwareSpec.
- Cases must be derived from the HardwareSpec behavior.
- Every critical behavior should have at least one explicit intent case.
- Include meaningful edge or boundary scenarios when they matter.
- Avoid redundant cases that check the exact same behavior.
- HardwareSpec is the source of truth.
- Your job is to decide WHAT should be verified, not to write low-level executable timing prose.
- Deterministic code will decide legal state setup, reset sequencing, clock-edge ordering, and exact expected values.
- Prefer semantic vector hints and behavior/scenario intent over executable text.
- If the HardwareSpec uses unsigned ports or signed=false, do not reinterpret the design as signed.

Schema expectations:
- Top-level fields: schema_version, module_name, design_type, strategy, cases, coverage_targets, assumptions, notes
- Return the full top-level object every time, including on repair.
- Do not return only a cases array, one corrected case, a patch, or explanatory prose.
- cases is a list of structured verification intent cases
- Each case must include: id, name, category, target_behavior, scenario, priority
- Optional fields per case: vector_hints, precondition_intent, edge_count_hint, coverage_tags, notes
- Use lowercase snake_case for each case id
- Use priority values 1, 2, or 3 only
- category MUST be one of: BASIC, FUNCTIONAL, RESET, CONTROL, EDGE_CASE, BOUNDARY, STATE_TRANSITION, ARITHMETIC, INVALID_OR_GUARDED, OTHER
- target_behavior may use grounded semantic behavior tokens such as ADD, SUB, AND, OR, RESET, MUX, ROUTING, PRIORITY_SELECT, NONZERO, DECODE, SHIFT_LEFT, SHIFT_RIGHT, INCREMENT, DECREMENT, HOLD, WRAPAROUND
- scenario MUST use only this verification-scenario vocabulary: BASIC, BOUNDARY, RESET_ASSERT, RESET_RELEASE, ENABLED_SINGLE_EDGE, ENABLED_MULTI_EDGE, DISABLED_HOLD, MAPPING, ARITHMETIC, LOGIC
- semantic feature kinds such as NONZERO, PRIORITY_SELECT, COMPARE, or CONDITIONAL belong in target_behavior, not in scenario
- vector_hints MUST be a JSON object whose keys are signal names and whose values are int, string, or boolean hints
- vector_hints are hints for legal DUT inputs only; never put DUT outputs or state outputs into vector_hints
- vector_hints may only use these HardwareSpec input names: {allowed_input_hint_text}
- do not include the clock signal in vector_hints; timing belongs to the deterministic compiler, not the AI intent
- vector_hints are optional advisory preferences only; it is acceptable to omit vector_hints entirely
- include vector_hints only when they add meaningful coverage value
- vector_hints must fit the declared input widths
- precondition_intent, if present, MUST be a JSON object with kind and optional signal, value, and description fields
- Do not emit executable fields such as setup, stimulus, expected, or covers
- coverage_targets, assumptions, and notes MUST be JSON arrays of strings
- target_behavior identifies the one primary hardware behavior being tested in this case
- coverage_tags are supporting labels only; do not move the main behavior token out of target_behavior
- semantic_features below are authoritative high-level behavior provenance
- when a semantic feature exists, keep target_behavior aligned to that feature instead of renaming it from low-level implementation shape
- for example, do not relabel PRIORITY_SELECT as generic ROUTING merely because executable semantics use nested SelectExpr nodes
- keep scenario focused on the testing situation, not the behavior identity

Grounded behavior rule:
- The HardwareSpec below grounds these supported behavior tokens: {grounded_behavior_text}
- Prefer those grounded behavior tokens exactly when they fit the spec
- Do not invent unsupported behavior tokens or unsupported hardware concepts

Structured semantic features:
{semantic_feature_text}
- These features describe the high-level semantic operations that exist in the HardwareSpec.
- Treat them as the authoritative meaning for behavior selection and case naming.
- If PRIORITY_SELECT is present, include scenarios that would distinguish true priority behavior from one-hot-only behavior, including at least one multiple-active-bit situation.
- If NONZERO is present, include scenarios that cover zero and nonzero source values.

Available structured semantic capabilities:
- {semantic_capability_text}
- When semantic_features do not already provide a stronger high-level token, prefer one of those semantic capability tokens for target_behavior when applicable.
- This keeps the AI verification vocabulary aligned with the deterministic compiler/evaluator vocabulary.

Small shape example:
{{
  "cases": [
    {{
      "id": "mux_select_zero",
      "name": "Route input a when select is zero",
      "category": "FUNCTIONAL",
      "target_behavior": "ROUTING",
      "scenario": "MAPPING",
      "priority": 1,
      "vector_hints": {{
        "select": 0,
        "a": 1,
        "b": 0
      }},
      "coverage_tags": ["select=0 mapping"]
    }}
  ],
  "coverage_targets": ["all specified routing paths"],
  "assumptions": ["cases are independent"],
  "notes": ["keep the plan concise and non-redundant"]
}}

Planning guidance:
- For mux or simple combinational logic: cover every specified select or control mapping and representative data behavior
- For ALU or arithmetic logic: cover every listed operation, opcode mapping, zero behavior, carry behavior if specified, and useful arithmetic boundary cases
- If a carry output exists for ADD behavior, include at least one case with target_behavior ADD and a boundary scenario that would exercise carry
- For counters or sequential logic: cover reset, clocked state updates, enable or hold behavior, boundary wrap behavior, and reset priority only if represented
- For shift registers or other sequential state machines: cover reset semantics, legal clocked state transitions, enable or hold behavior, and only the state transitions actually defined by the HardwareSpec
- For sequential designs, every case is independent
- Do not assume a previous case established the DUT state
- Reset deassertion is not initialization
- If a case needs a boundary state, express that through precondition_intent or by giving enough vector/edge hints for deterministic legal setup
- Deterministic compilation selects the final legal vectors, reset sequence, state setup, and timing
- Use vector_hints only to suggest useful operand/control preferences, never to define validity of the case
- Do not invent major behavioral concepts that are absent from the HardwareSpec, such as wraparound, saturation, carry, borrow, FIFO full/empty rules, or reset priority when they are not specified
- Keep vector hints grounded in DUT inputs and behavioral scenarios, not DUT outputs

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
    """Build the repair prompt for verification-intent failures."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    joined_errors = "\n".join(f"- {error}" for error in errors) or "- Unknown verification-plan generation failure"
    field_guidance = "\n".join(build_field_guidance(error) for error in errors if build_field_guidance(error))
    return f"""You previously generated an invalid verification intent plan.

Return repaired JSON only.
- No Markdown.
- No explanations.
- JSON only.
- Preserve the intended verification behaviors where possible.
- Fix only the verification intent plan.
- Directly correct every listed validation error.
- Fix the semantic cause of each error, not just the wording.
- Do not merely rename or rephrase cases if the underlying problem remains.
- Preserve valid parts of the previous intent where possible.
- Maintain HardwareSpec semantics exactly.
- Do not introduce output/state vector hints.
- Return a complete corrected JSON object, not a partial patch.
- Do not invent new hardware behavior.
- Do not generate SystemVerilog or testbench code.
- Preserve valid intent categories, target behaviors, scenarios, and vector choices where possible.
- Deterministic code will compute executable timing and expected values, so focus on WHAT should be verified.
- Invalid optional vector hints do not need elaborate repair; if unsure, omit them entirely.
- Every repair response must replace the full VerificationIntentPlan object.
- Required top-level fields are: schema_version, module_name, design_type, strategy, cases, coverage_targets, assumptions, notes.
- scenario must use only the verification-scenario vocabulary from the main prompt.
- semantic feature kinds such as NONZERO or PRIORITY_SELECT belong in target_behavior, not scenario.

If an error reports ILLEGAL_OUTPUT_DRIVE:
- Remove output/state hints from vector_hints.
- Vector hints may only describe DUT inputs, and they are optional.

If an error reports INVALID_VECTOR_HINT:
- Fix the specific vector_hints entry named in the error.
- Use only legal DUT input names.
- Do not use the clock signal as a normal vector hint.
- Ensure any supplied value fits the declared width, or omit the hint entirely.

If an error reports UNESTABLISHED_SEQUENTIAL_STATE:
- Every sequential case is independent; do not assume state from a previous case.
- Reset deassertion does not initialize state.
- If state setup is required, express that with target behavior, scenario, edge_count_hint, and legal precondition_intent rather than output assignments.
- Asynchronous reset assertion does not require a clock edge.
- Do not guess an initial state.

If an error reports UNSUPPORTED_BEHAVIOR:
- Remove or replace invented behavior that is not grounded in the HardwareSpec.
- For example, do not request wraparound for a shift register unless the HardwareSpec defines wraparound.

If an error reports INVALID_SCENARIO_VOCABULARY:
- Move semantic behavior tokens out of scenario.
- Keep target_behavior aligned to the grounded semantic feature or behavior identity.
- Use only verification-scenario tokens such as BASIC, BOUNDARY, MAPPING, RESET_ASSERT, RESET_RELEASE, ENABLED_SINGLE_EDGE, ENABLED_MULTI_EDGE, DISABLED_HOLD, ARITHMETIC, or LOGIC in scenario.

If an error reports INVALID_VERIFICATION_INTENT_ENVELOPE:
- Return the complete VerificationIntentPlan JSON object, not a fragment.
- Include all required top-level fields: schema_version, module_name, design_type, strategy, cases, coverage_targets, assumptions, notes.
- Do not return only cases, a partial fix, or explanatory prose.

Field-specific repair guidance:
{field_guidance or "- No additional field-specific guidance was derived from the current errors."}

Validated HardwareSpec JSON:
{spec_json}

Previous invalid model output:
{previous_output}

Errors to fix:
{joined_errors}
"""


def build_field_guidance(error: str) -> str:
    """Turn one validation error into short field-specific repair guidance when obvious."""

    location = error.split(":", 1)[0].strip()
    if "vector_hints" in location:
        return f"- Fix `{location}` by using a legal DUT input hint key and a parseable literal/boolean value."
    if "target_behavior" in location:
        return f"- Fix `{location}` by using one grounded primary behavior token in `target_behavior`."
    if "scenario" in location:
        return f"- Fix `{location}` by using one supported scenario token in `scenario`."
    if "precondition_intent" in location:
        return f"- Fix `{location}` by using a structured `precondition_intent` object instead of executable prose."
    if "coverage_tags" in location:
        return f"- Fix `{location}` by keeping only descriptive labels there; the primary behavior belongs in `target_behavior`."
    return ""
