from rtl_assistant.models.hardware_spec import HardwareSpec

RTL_GENERATION_PROMPT_VERSION = "1.0"


def build_rtl_generation_prompt(hardware_spec: HardwareSpec) -> str:
    """Build the primary prompt for SystemVerilog RTL generation."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    return f"""You are a careful hardware RTL generator.

Task:
Generate synthesizable SystemVerilog RTL for exactly one module from the validated HardwareSpec below.

Rules:
- Return RTL only.
- Do not return Markdown.
- Do not wrap the RTL in triple backticks.
- Do not include explanations.
- Generate exactly one module.
- Use the exact module_name from the HardwareSpec.
- Use exactly the specified external ports.
- Do not add extra external ports.
- Preserve port directions, widths, and signedness.
- Preserve combinational vs sequential semantics.
- Preserve clock edge, reset type, reset polarity, reset values, and reset priority semantics.
- Preserve behavior.operations, behavior.rules, and behavior.assumptions.
- Do not generate a testbench.

Coding rules:
- Generate synthesizable SystemVerilog only.
- Prefer modern SystemVerilog `logic` instead of Verilog-style `reg`.
- No #delays.
- No $display, $finish, $dumpfile, or $dumpvars.
- No initial blocks.
- No DPI, classes, randomization, or simulation-only constructs.
- For combinational logic, prefer always_comb or continuous assignments and avoid inferred latches.
- Any signal assigned inside always_comb or always_ff must be declared as a variable, preferably `logic`.
- Procedurally assigned output ports should be declared explicitly as `output logic ...`.
- Ensure combinational outputs are assigned on every path.
- For 1-bit ports, prefer scalar syntax such as `input logic a` instead of `[0:0]`.
- Use sensible defaults in case statements where required.
- For sequential logic, use always_ff.
- Use the correct posedge or negedge.
- Use nonblocking assignments for sequential state updates.
- Avoid redundant self-assignments used only to hold state, such as `count <= count;`, when omitting the assignment naturally preserves state.

Validated HardwareSpec JSON:
{spec_json}
"""


def build_rtl_repair_prompt(
    hardware_spec: HardwareSpec,
    previous_rtl: str,
    errors: list[str],
) -> str:
    """Build the repair prompt used after local extraction/sanity failure."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    joined_errors = "\n".join(f"- {error}" for error in errors) or "- Unknown RTL generation failure"
    return f"""You previously generated invalid SystemVerilog RTL.

Return repaired RTL only.
- No Markdown.
- No explanations.
- Exactly one SystemVerilog module.
- Preserve the exact external interface from the HardwareSpec.
- Repair only the RTL.

Validated HardwareSpec JSON:
{spec_json}

Previous generated RTL:
{previous_rtl}

Errors to fix:
{joined_errors}
"""
