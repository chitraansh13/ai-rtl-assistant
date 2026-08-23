from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtl_assistant.spec.prompts import (
    build_hardware_intent_json_repair_prompt,
    build_hardware_intent_prompt,
    build_hardware_intent_repair_prompt,
    build_requirement_analysis_prompt,
    build_requirement_analysis_repair_prompt,
)


class HardwareIntentPromptContentTests(unittest.TestCase):
    def test_generation_prompt_distinguishes_case_select_and_priority_select(self):
        prompt = build_hardware_intent_prompt("Create a simple combinational datapath.")
        self.assertIn("CASE_SELECT: selector/opcode/mode dispatch", prompt)
        self.assertIn("PRIORITY_SELECT: ONLY for choosing which source vector bit wins by priority.", prompt)
        self.assertIn("NEVER use PRIORITY_SELECT as switch/case or opcode dispatch.", prompt)

    def test_generation_prompt_contains_zero_and_carry_guidance(self):
        prompt = build_hardware_intent_prompt("Create a simple combinational datapath.")
        self.assertIn("A zero flag must use EQ(x, 0), not NONZERO(x).", prompt)
        self.assertIn("unsigned carry-out for 8-bit add", prompt)
        self.assertIn('"type":"extend"', prompt)
        self.assertIn('"type":"bit_select"', prompt)

    def test_generation_prompt_preserves_fixed_width_and_conditional_output_semantics(self):
        prompt = build_hardware_intent_prompt("Create a simple combinational datapath.")
        self.assertIn("use ordinary fixed-width ADD or SUB", prompt)
        self.assertIn("Do not extend ordinary fixed-width arithmetic", prompt)
        self.assertIn("assign X a CONDITIONAL", prompt)
        self.assertIn("BIT_SELECT(expression,index) already produces the selected bit value", prompt)
        self.assertIn('EQ(A,B) produces the 1-bit result of comparing A and B', prompt)

    def test_generation_prompt_forbids_invented_operators(self):
        prompt = build_hardware_intent_prompt("Create a simple combinational datapath.")
        self.assertIn("Do not invent operators such as CARRY, MAX, MUX, ALU_OP, ZERO_FLAG, or COMPARE_GT.", prompt)

    def test_generation_prompt_requires_port_direction_on_every_port(self):
        prompt = build_hardware_intent_prompt("Create a simple combinational datapath.")
        self.assertIn('EVERY port object MUST contain', prompt)
        self.assertIn('"direction": "input" | "output" | "inout"', prompt)
        self.assertIn('{"name":"a","width":8,"direction":"input","signed":false}', prompt)
        self.assertIn('{"name":"y","width":8,"direction":"output","signed":false}', prompt)
        self.assertIn("every port has direction", prompt)

    def test_repair_prompt_demands_complete_json_and_targeted_guidance(self):
        prompt = build_hardware_intent_repair_prompt(
            "Create a datapath.",
            '{"type":"bad"}',
            [
                "UNSUPPORTED_HARDWARE_INTENT: invented CARRY operator",
                "priority_select used as opcode dispatch",
                "NONZERO used for zero flag",
            ],
        )
        self.assertIn("Return the COMPLETE corrected HardwareIntent object, not a patch or diff.", prompt)
        self.assertIn("Return corrected JSON only.", prompt)
        self.assertIn("Use CASE_SELECT for selector-value dispatch.", prompt)
        self.assertIn("Do not invent a CARRY operator.", prompt)
        self.assertIn("A zero flag must use EQ(x,0).", prompt)

    def test_repair_prompt_contains_missing_port_direction_guidance(self):
        prompt = build_hardware_intent_repair_prompt(
            "Create a datapath.",
            '{"ports":[{"name":"a","width":8,"signed":false}]}',
            [
                "ports -> 0 -> direction: Field required",
                "ports -> 1 -> direction: Field required",
            ],
        )
        self.assertIn("Every port requires direction.", prompt)
        self.assertIn("Use 'input' for requirement inputs and 'output' for requirement outputs", prompt)

    def test_malformed_json_repair_requires_complete_nested_hardware_intent(self):
        prompt = build_hardware_intent_json_repair_prompt(
            "Create a combinational datapath.",
            '{"type":"conditional","condition":{"type":"signal","name":"sel"}',
            "INVALID_HARDWARE_INTENT_JSON: Expecting ',' delimiter",
        )
        self.assertIn("Return one COMPLETE HardwareIntent object", prompt)
        self.assertIn("matching {} objects and [] arrays", prompt)
        self.assertIn("Keep every nested expression field inside its parent expression object", prompt)
        self.assertIn('"when_true"', prompt)
        self.assertIn('"when_false"', prompt)
        self.assertIn('"type":"bit_select"', prompt)
        self.assertIn('"type":"extend"', prompt)
        self.assertIn("Keep N-bit ADD/SUB assigned to an N-bit target fixed-width", prompt)
        self.assertIn('Preserve "X is E when C, otherwise D" as CONDITIONAL', prompt)
        self.assertIn("BIT_SELECT directly produces a bit value; EQ produces a boolean comparison result", prompt)
        self.assertIn("INVALID_HARDWARE_INTENT_JSON", prompt)

    def test_schema_repair_preserves_width_and_value_semantics(self):
        prompt = build_hardware_intent_repair_prompt(
            "Create a combinational datapath.",
            '{"schema_version":"1.0"}',
            ["INTENT_WIDTH_MISMATCH: conditional branch width does not match target"],
        )
        self.assertIn("Keep fixed-width ADD/SUB fixed-width", prompt)
        self.assertIn("use CONDITIONAL(condition=C, when_true=E, when_false=D)", prompt)
        self.assertIn("EQ(A,B) produces a boolean comparison result", prompt)
        self.assertIn("BIT_SELECT(expr,k) directly produces the selected bit value", prompt)

    def test_requirement_analysis_prompt_shows_valid_json_shape(self):
        prompt = build_requirement_analysis_prompt("Create a datapath.")
        self.assertIn('"explicitly_specified":["input_width","output_width","opcode_mapping"]', prompt)
        self.assertIn('"clarification_questions":[{"id":"signedness"', prompt)
        self.assertIn('"assumptions":[]', prompt)

    def test_requirement_analysis_repair_prompt_mentions_arrays_vs_objects(self):
        prompt = build_requirement_analysis_repair_prompt(
            "Create a datapath.",
            '["input_width":8]',
            ["INVALID_ANALYSIS_JSON: Expecting ',' delimiter"],
        )
        self.assertIn("Arrays contain values only, never key:value pairs.", prompt)
        self.assertIn("Objects use {} and lists use [].", prompt)


if __name__ == "__main__":
    unittest.main()
