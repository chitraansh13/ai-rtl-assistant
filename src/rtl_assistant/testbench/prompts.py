from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.verification_plan import VerificationPlan

TESTBENCH_PROMPT_VERSION = "1.2"


def build_testbench_generation_prompt(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
) -> str:
    """Build the primary prompt for self-checking SystemVerilog testbench generation."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    plan_json = verification_plan.model_dump_json(indent=2)
    return f"""You are a careful hardware testbench generator.

Task:
Generate exactly one self-checking SystemVerilog testbench module from the validated HardwareSpec and VerificationPlan below.

Return rules:
- Return ONLY SystemVerilog.
- Do not return Markdown.
- Do not wrap the output in triple backticks.
- Do not include explanations.
- Generate exactly one testbench module.
- Do not redefine the DUT module.
- Instantiate the exact DUT module named in the HardwareSpec.

Testbench requirements:
- Use the full HardwareSpec and VerificationPlan as the source of truth.
- Declare signals with widths matching the HardwareSpec.
- Drive only DUT input ports.
- Never drive DUT output ports.
- Implement EVERY supplied VerificationPlan test case.
- Do not merge, drop, skip, or silently rewrite away test cases.
- Preserve every VerificationPlan test_case.id in a comment, $display, or another clear marker.
- Execute test cases in VerificationPlan order unless a different order is required for correctness.
- For each VerificationPlan test case, check exactly the DUT outputs represented in that test case's expected list.
- Do not invent expected values for outputs that are absent from a test case's expected list.
- Prefer explicit inline per-test checking for VerificationPlan-driven tests.
- Do NOT use a generic shared output-checking task when different tests check different subsets of DUT outputs.
- Do not force all tests into one fixed expected-output signature when the VerificationPlan does not require that.
- Simple helpers for unrelated infrastructure are acceptable, but each VerificationPlan test's actual output comparisons should remain inline in that test's own section.
- Make tests independently reproducible as far as practical.
- Generate self-checking logic with PASS/FAIL reporting.
- Maintain a failed-test counter.
- Before $finish, print a final failed-test summary such as `$display("Failed tests: %0d", failed_tests);`.
- Include $finish.
- Use readable educational testbench code, not UVM or complex infrastructure.
- Use one deterministic main stimulus/test sequence for DUT-driving behavior.
- Do not create multiple concurrent stimulus processes that write the same DUT inputs.
- A separate clock-generation process is acceptable for sequential designs, but DUT test cases must still run through one main sequence.

Clock and reset:
- If the design is sequential, generate a simple clock process using the HardwareSpec clock signal.
- Respect the configured active clock edge.
- Respect synchronous vs asynchronous reset semantics and reset polarity.
- Apply inputs before the relevant active edge and observe outputs after the state update at a safe observation point.
- A small delay after active edges is acceptable when needed for deterministic checking.
- If the design is combinational and the HardwareSpec has no clock port, do NOT declare a clock signal and do NOT generate clock logic.
- If the design is combinational and the HardwareSpec has no reset port, do NOT invent reset signals or reset sequencing.
- For combinational designs, declare only DUT-facing signals from the HardwareSpec plus local helper variables needed for checking.
- For combinational designs, use a small settling delay such as #1 after changing inputs before checking outputs.
- Delays are timing controls, not generic line prefixes.
- For combinational tests, apply the full stimulus first, then wait once, then perform the check.
- Preferred combinational pattern:
  a = ...;
  b = ...;
  opcode = ...;
  #1;
  if (...) begin
      ...
  end
- Never place delay controls directly before structural keywords such as begin, end, or else.
- Avoid unnecessary delays inside PASS/FAIL bookkeeping such as before $display or failed_tests++.
- For combinational designs, do not create a clock process or reset infrastructure unless those ports actually exist in the HardwareSpec.

Self-checking style:
- Prefer clear comparison logic such as:
  if (signal !== expected) begin
      $display("FAIL: ...");
      failed_tests++;
  end else begin
      $display("PASS: ...");
  end
- Use valid SystemVerilog boolean operators such as && and || inside procedural conditions.
- Never use English words like `and` or `or` inside an if-condition expression.
- For checks with multiple expected outputs, construct one mismatch predicate per output and combine them with logical OR.
- A test must enter the FAIL branch when any checked output mismatches.
- PASS only when all checked outputs match.
- Each inline test section should preserve its test_case.id and contain its own explicit comparisons for exactly that test's expected outputs.
- Preferred multi-output pattern:
  if (out1 !== expected1 || out2 !== expected2 || out3 !== expected3) begin
      $display("FAIL: test_id");
      failed_tests++;
  end else begin
      $display("PASS: test_id");
  end
- Do not combine output-mismatch predicates with &&, because that would only fail when every checked output is wrong.

Validated HardwareSpec JSON:
{spec_json}

Validated VerificationPlan JSON:
{plan_json}
"""


def build_testbench_repair_prompt(
    hardware_spec: HardwareSpec,
    verification_plan: VerificationPlan,
    previous_testbench: str,
    errors: list[str],
) -> str:
    """Build the repair prompt for structural or semantic testbench failures."""

    spec_json = hardware_spec.model_dump_json(indent=2)
    plan_json = verification_plan.model_dump_json(indent=2)
    joined_errors = "\n".join(f"- {error}" for error in errors) or "- Unknown testbench generation failure"
    return f"""You previously generated an invalid SystemVerilog testbench.

Return repaired SystemVerilog only.
- No Markdown.
- No explanations.
- Preserve valid parts of the testbench where possible.
- Fix the actual structural or semantic cause of every listed error.
- Do not redefine the DUT.
- Do not invent new ports or behavior.
- Keep the HardwareSpec and VerificationPlan semantics exactly.
- If a validation error reports missing test-case implementation, add the missing VerificationPlan test cases and preserve their ids in the generated testbench.
- If a validation error reports multiple stimulus processes, repair the testbench so DUT-driving behavior executes through one deterministic main stimulus sequence.
- Do not fix these errors merely by renaming comments; repair the actual execution structure.

Validated HardwareSpec JSON:
{spec_json}

Validated VerificationPlan JSON:
{plan_json}

Previous invalid testbench:
{previous_testbench}

Errors to fix:
{joined_errors}
"""
