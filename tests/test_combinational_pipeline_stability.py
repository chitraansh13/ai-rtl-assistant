from __future__ import annotations

import sys
import unittest


class BehavioralObligationRegressionTests(unittest.TestCase):
    @staticmethod
    def _behavior_question(target: str):
        from rtl_assistant.models.llm import ClarificationQuestion

        semantic_key = f"{target}_behavior"
        return ClarificationQuestion(
            id=semantic_key,
            field=semantic_key,
            semantic_key=semantic_key,
            question=f"What should {target} do outside the stated condition?",
            reason="The conditional output behavior may be incomplete.",
            required=True,
        )

    def test_complete_conditional_output_rule_is_resolved(self):
        from rtl_assistant.models.llm import RequirementAnalysis
        from rtl_assistant.spec.ai_parser import merge_with_local_ambiguity_policy

        requirement = (
            "Create a combinational module with an output alarm. "
            "alarm should be 1 when fault is active, otherwise 0."
        )
        analysis = RequirementAnalysis(
            ready=False,
            missing_critical=["alarm_behavior"],
            ambiguous=["alarm_behavior"],
            clarification_questions=[self._behavior_question("alarm")],
        )

        merged = merge_with_local_ambiguity_policy(requirement, analysis)

        self.assertTrue(merged.ready)
        self.assertEqual(merged.clarification_questions, [])
        self.assertEqual(len(merged.behavioral_obligations), 1)
        self.assertTrue(merged.behavioral_obligations[0].complete)

    def test_partial_conditional_output_rule_remains_unresolved(self):
        from rtl_assistant.models.llm import RequirementAnalysis
        from rtl_assistant.spec.ai_parser import merge_with_local_ambiguity_policy

        requirement = (
            "Create a combinational module with an output alarm. "
            "alarm should be 1 when fault is active."
        )
        analysis = RequirementAnalysis(
            ready=False,
            missing_critical=["alarm_behavior"],
            ambiguous=["alarm_behavior"],
            clarification_questions=[self._behavior_question("alarm")],
        )

        merged = merge_with_local_ambiguity_policy(requirement, analysis)

        self.assertFalse(merged.ready)
        self.assertEqual([question.semantic_key for question in merged.clarification_questions], ["alarm_behavior"])
        self.assertEqual(len(merged.behavioral_obligations), 1)
        self.assertFalse(merged.behavioral_obligations[0].complete)

    def test_custom_output_names_use_the_same_structural_rule_detection(self):
        from rtl_assistant.spec.ai_parser import detect_behavioral_obligations

        for target in ("alarm", "flag_custom", "result_status"):
            obligations = detect_behavioral_obligations(
                f"{target} should equal active_value if enable is 1, otherwise inactive_value."
            )
            self.assertEqual(len(obligations), 1)
            self.assertEqual(obligations[0].target, target)
            self.assertTrue(obligations[0].complete)

    def test_original_behavior_survives_post_clarification_analysis(self):
        from rtl_assistant.models.llm import BehavioralObligationSource, RequirementAnalysis
        from rtl_assistant.spec.ai_parser import merge_with_local_ambiguity_policy

        enriched_requirement = (
            "Create a combinational module with an output result_status. "
            "result_status should be ready_value when enable is 1, otherwise idle_value."
            "\n\nClarified requirements:\n- Signedness: unsigned"
        )

        merged = merge_with_local_ambiguity_policy(
            enriched_requirement,
            RequirementAnalysis(ready=True),
        )

        self.assertTrue(merged.ready)
        self.assertEqual(len(merged.behavioral_obligations), 1)
        self.assertEqual(merged.behavioral_obligations[0].target, "result_status")
        self.assertEqual(
            merged.behavioral_obligations[0].source,
            BehavioralObligationSource.EXPLICIT_REQUIREMENT,
        )

    def test_complete_behavior_supplied_by_clarification_is_preserved(self):
        from rtl_assistant.models.llm import BehavioralObligationSource
        from rtl_assistant.spec.ai_parser import detect_behavioral_obligations

        enriched_requirement = (
            "Create a combinational module with an output alarm."
            "\n\nClarified requirements:\n"
            "- Alarm behavior: alarm should be 1 when fault is active, otherwise 0"
        )

        obligations = detect_behavioral_obligations(enriched_requirement)

        self.assertEqual(len(obligations), 1)
        self.assertTrue(obligations[0].complete)
        self.assertEqual(obligations[0].source, BehavioralObligationSource.CLARIFICATION)

    def test_generation_and_repair_prompts_receive_resolved_obligations(self):
        from rtl_assistant.models.llm import RequirementAnalysis
        from rtl_assistant.spec.ai_parser import enrich_requirement_for_generation, merge_with_local_ambiguity_policy
        from rtl_assistant.spec.prompts import (
            build_hardware_intent_json_repair_prompt,
            build_hardware_intent_prompt,
            build_hardware_intent_repair_prompt,
        )

        requirement = (
            "Create a combinational module with an output flag_custom. "
            "flag_custom should be selected_bit when enable is 1, otherwise 0."
        )
        analysis = merge_with_local_ambiguity_policy(requirement, RequirementAnalysis(ready=True))
        handoff = enrich_requirement_for_generation(requirement, analysis)

        self.assertIn("RESOLVED REQUIREMENT FACTS (authoritative)", handoff)
        self.assertIn("target=flag_custom", handoff)
        self.assertIn("condition=enable is 1", handoff)
        self.assertIn("when_true=selected_bit", handoff)
        self.assertIn("when_false=0", handoff)
        self.assertIn("target=flag_custom", build_hardware_intent_prompt(handoff))
        self.assertIn(
            "target=flag_custom",
            build_hardware_intent_repair_prompt(handoff, "{}", ["schema error"]),
        )
        self.assertIn(
            "target=flag_custom",
            build_hardware_intent_json_repair_prompt(handoff, "{", "JSON parser error"),
        )
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
from rtl_assistant.models.compiled_verification_plan import CompiledVerificationCase
from rtl_assistant.models.hardware_intent import (
    CombinationalHardwareIntent,
    HardwareIntent,
    IntentAssignment,
    IntentBinaryExpr,
    IntentBinaryOp,
    IntentConditionalExpr,
    IntentPrioritySelectExpr,
    IntentSignalExpr,
    IntentUnaryExpr,
    IntentUnaryOp,
    PriorityDirection,
)
from rtl_assistant.models.hardware_spec import BehaviorSpec, DesignType, HardwareSpec, PortDirection, PortRole, PortSpec
from rtl_assistant.models.llm import ClarificationQuestion, RequirementAnalysis, RequirementParseResult, RequirementStatus
from rtl_assistant.models.semantics import (
    BinaryExpr,
    BinarySemanticOp,
    BitSelectExpr,
    CombinationalSemantics,
    HardwareSemantics,
    LiteralExpr,
    SelectExpr,
    SemanticAssignment,
    SignalExpr,
    UnaryExpr,
    UnarySemanticOp,
)
from rtl_assistant.models.verification_common import TestCategory
from rtl_assistant.models.verification_intent import VerificationIntentCase, VerificationIntentPlan
from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics
from rtl_assistant.spec.ai_parser import (
    AmbiguityPolicyInconsistencyError,
    finalize_requirement_analysis_state,
    merge_with_local_ambiguity_policy,
    normalize_hardware_intent_payload,
    validate_hardware_intent_envelope,
)
from rtl_assistant.testbench.ir import ExpectedCheck, InputAssignment, TestbenchAction, TestbenchActionType, TestbenchCase, TestbenchPlan
from rtl_assistant.testbench.renderer import render_action
from rtl_assistant.verification_plan.compiler import (
    VerificationCompilationError,
    compile_verification_intent_plan,
    extract_input_vector,
    is_priority_competition_vector,
)
from rtl_assistant.verification_plan.generator import validate_verification_intent_envelope


def make_port(name: str, direction: PortDirection, width: int = 1, role: PortRole = PortRole.DATA) -> PortSpec:
    return PortSpec(name=name, direction=direction, width=width, role=role)


def build_mux_spec() -> HardwareSpec:
    intent = HardwareIntent(
        module_name="mux2",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("a", PortDirection.INPUT, width=1, role=PortRole.DATA),
            make_port("b", PortDirection.INPUT, width=1, role=PortRole.DATA),
            make_port("sel", PortDirection.INPUT, width=1, role=PortRole.CONTROL),
            make_port("y", PortDirection.OUTPUT, width=1, role=PortRole.DATA),
        ],
        combinational_intent=CombinationalHardwareIntent(
            assignments=[
                IntentAssignment(
                    target="y",
                    expression=IntentConditionalExpr(
                        condition=IntentSignalExpr(name="sel"),
                        when_true=IntentSignalExpr(name="b"),
                        when_false=IntentSignalExpr(name="a"),
                    ),
                )
            ]
        ),
        behavior=BehaviorSpec(description="2:1 mux", operations=["ROUTING"], rules=[], assumptions=[]),
    )
    return compile_hardware_intent(intent)


def build_add_sub_spec() -> HardwareSpec:
    intent = HardwareIntent(
        module_name="conditional_add_sub",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("a", PortDirection.INPUT, width=6, role=PortRole.DATA),
            make_port("b", PortDirection.INPUT, width=6, role=PortRole.DATA),
            make_port("mode", PortDirection.INPUT, width=1, role=PortRole.CONTROL),
            make_port("y", PortDirection.OUTPUT, width=6, role=PortRole.DATA),
        ],
        combinational_intent=CombinationalHardwareIntent(
            assignments=[
                IntentAssignment(
                    target="y",
                    expression=IntentConditionalExpr(
                        condition=IntentSignalExpr(name="mode"),
                        when_true=IntentBinaryExpr(
                            op=IntentBinaryOp.SUB,
                            left=IntentSignalExpr(name="a"),
                            right=IntentSignalExpr(name="b"),
                        ),
                        when_false=IntentBinaryExpr(
                            op=IntentBinaryOp.ADD,
                            left=IntentSignalExpr(name="a"),
                            right=IntentSignalExpr(name="b"),
                        ),
                    ),
                )
            ]
        ),
        behavior=BehaviorSpec(description="conditional add/sub datapath", operations=["ADD", "SUB"], rules=[], assumptions=[]),
    )
    return compile_hardware_intent(intent)


def build_comparator_spec() -> HardwareSpec:
    intent = HardwareIntent(
        module_name="cmp2",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("a", PortDirection.INPUT, width=2, role=PortRole.DATA),
            make_port("b", PortDirection.INPUT, width=2, role=PortRole.DATA),
            make_port("eq", PortDirection.OUTPUT, width=1, role=PortRole.STATUS),
            make_port("gt", PortDirection.OUTPUT, width=1, role=PortRole.STATUS),
            make_port("lt", PortDirection.OUTPUT, width=1, role=PortRole.STATUS),
        ],
        combinational_intent=CombinationalHardwareIntent(
            assignments=[
                IntentAssignment(
                    target="eq",
                    expression=IntentBinaryExpr(
                        op=IntentBinaryOp.EQ,
                        left=IntentSignalExpr(name="a"),
                        right=IntentSignalExpr(name="b"),
                    ),
                ),
                IntentAssignment(
                    target="gt",
                    expression=IntentBinaryExpr(
                        op=IntentBinaryOp.GT,
                        left=IntentSignalExpr(name="a"),
                        right=IntentSignalExpr(name="b"),
                    ),
                ),
                IntentAssignment(
                    target="lt",
                    expression=IntentBinaryExpr(
                        op=IntentBinaryOp.LT,
                        left=IntentSignalExpr(name="a"),
                        right=IntentSignalExpr(name="b"),
                    ),
                ),
            ]
        ),
        behavior=BehaviorSpec(description="unsigned comparator", operations=["EQ", "GT", "LT"], rules=[], assumptions=[]),
    )
    return compile_hardware_intent(intent)


def build_add_xor_spec() -> HardwareSpec:
    intent = HardwareIntent(
        module_name="conditional_add_xor",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("a", PortDirection.INPUT, width=4, role=PortRole.DATA),
            make_port("b", PortDirection.INPUT, width=4, role=PortRole.DATA),
            make_port("sel", PortDirection.INPUT, width=1, role=PortRole.CONTROL),
            make_port("y", PortDirection.OUTPUT, width=4, role=PortRole.DATA),
        ],
        combinational_intent=CombinationalHardwareIntent(
            assignments=[
                IntentAssignment(
                    target="y",
                    expression=IntentConditionalExpr(
                        condition=IntentSignalExpr(name="sel"),
                        when_true=IntentBinaryExpr(
                            op=IntentBinaryOp.BIT_XOR,
                            left=IntentSignalExpr(name="a"),
                            right=IntentSignalExpr(name="b"),
                        ),
                        when_false=IntentBinaryExpr(
                            op=IntentBinaryOp.ADD,
                            left=IntentSignalExpr(name="a"),
                            right=IntentSignalExpr(name="b"),
                        ),
                    ),
                )
            ]
        ),
        behavior=BehaviorSpec(description="conditional add/xor datapath", operations=["ADD", "BIT_XOR"], rules=[], assumptions=[]),
    )
    return compile_hardware_intent(intent)


def build_priority_spec() -> HardwareSpec:
    intent = HardwareIntent(
        module_name="priority8",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("data_in", PortDirection.INPUT, width=8, role=PortRole.DATA),
            make_port("encoded_out", PortDirection.OUTPUT, width=3, role=PortRole.DATA),
            make_port("valid", PortDirection.OUTPUT, width=1, role=PortRole.STATUS),
        ],
        combinational_intent=CombinationalHardwareIntent(
            assignments=[
                IntentAssignment(
                    target="encoded_out",
                    expression=IntentPrioritySelectExpr(
                        source_signal="data_in",
                        direction=PriorityDirection.HIGHEST_INDEX_FIRST,
                    ),
                ),
                IntentAssignment(
                    target="valid",
                    expression=IntentUnaryExpr(
                        op=IntentUnaryOp.NONZERO,
                        operand=IntentSignalExpr(name="data_in"),
                    ),
                ),
            ]
        ),
        behavior=BehaviorSpec(description="priority select with valid output", operations=["PRIORITY_SELECT", "NONZERO"], rules=[], assumptions=[]),
    )
    return compile_hardware_intent(intent)


def build_bitselect_spec() -> HardwareSpec:
    return HardwareSpec(
        module_name="bitselect_conditional",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("data_in", PortDirection.INPUT, width=4, role=PortRole.DATA),
            make_port("invert", PortDirection.INPUT, width=1, role=PortRole.CONTROL),
            make_port("y", PortDirection.OUTPUT, width=1, role=PortRole.STATUS),
        ],
        semantics=HardwareSemantics(
            combinational=CombinationalSemantics(
                assignments=[
                    SemanticAssignment(
                        target="y",
                        expression=SelectExpr(
                            condition=SignalExpr(name="invert"),
                            when_true=UnaryExpr(
                                op=UnarySemanticOp.LOGICAL_NOT,
                                operand=BitSelectExpr(signal=SignalExpr(name="data_in"), index=2),
                            ),
                            when_false=BitSelectExpr(signal=SignalExpr(name="data_in"), index=2),
                        ),
                    )
                ]
            )
        ),
        behavior=BehaviorSpec(description="bit-select conditional design", operations=["SELECT"], rules=[], assumptions=[]),
    )


def build_decoder_spec() -> HardwareSpec:
    sel = SignalExpr(name="sel")
    return HardwareSpec(
        module_name="decoder2to4",
        design_type=DesignType.COMBINATIONAL,
        ports=[
            make_port("sel", PortDirection.INPUT, width=2, role=PortRole.DATA),
            make_port("y", PortDirection.OUTPUT, width=4, role=PortRole.DATA),
        ],
        semantics=HardwareSemantics(
            combinational=CombinationalSemantics(
                assignments=[
                    SemanticAssignment(
                        target="y",
                        expression=SelectExpr(
                            condition=BinaryExpr(
                                op=BinarySemanticOp.EQ,
                                left=sel,
                                right=LiteralExpr(value=0, width=2),
                            ),
                            when_true=LiteralExpr(value=0b0001, width=4),
                            when_false=SelectExpr(
                                condition=BinaryExpr(
                                    op=BinarySemanticOp.EQ,
                                    left=sel,
                                    right=LiteralExpr(value=1, width=2),
                                ),
                                when_true=LiteralExpr(value=0b0010, width=4),
                                when_false=SelectExpr(
                                    condition=BinaryExpr(
                                        op=BinarySemanticOp.EQ,
                                        left=sel,
                                        right=LiteralExpr(value=2, width=2),
                                    ),
                                    when_true=LiteralExpr(value=0b0100, width=4),
                                    when_false=LiteralExpr(value=0b1000, width=4),
                                ),
                            ),
                        ),
                    )
                ]
            )
        ),
        behavior=BehaviorSpec(description="2-to-4 decoder mapping", operations=["DECODE"], rules=[], assumptions=[]),
    )


class CombinationalPipelineStabilityTests(unittest.TestCase):
    def test_hardware_intent_design_type_validates_to_shared_enum(self) -> None:
        intent = HardwareIntent(
            module_name="intent_type_contract",
            design_type="combinational",
            ports=[
                make_port("a", PortDirection.INPUT, width=1, role=PortRole.DATA),
                make_port("y", PortDirection.OUTPUT, width=1, role=PortRole.DATA),
            ],
            combinational_intent=CombinationalHardwareIntent(
                assignments=[
                    IntentAssignment(
                        target="y",
                        expression=IntentSignalExpr(name="a"),
                    )
                ]
            ),
        )
        self.assertIs(intent.design_type, DesignType.COMBINATIONAL)

    def test_post_clarification_selector_mapping_stays_resolved(self) -> None:
        original_requirement = (
            "Create an 8-bit combinational module with 8-bit inputs a and b, a 2-bit input op, and outputs y, zero, "
            "and carry. When op is 0, y should equal a plus b. When op is 1, y should equal a minus b. When op is 2, "
            "y should equal a XOR b. When op is 3, output a if a is greater than b, otherwise output b. "
            "zero should be 1 when y is zero. carry should be the addition carry-out only when op is 0."
        )
        pre_answer_analysis = RequirementAnalysis(
            ready=False,
            explicitly_specified=[],
            safely_inferred=[],
            missing_critical=["signedness", "opcode_mapping"],
            ambiguous=["signedness", "opcode_mapping"],
            clarification_questions=[
                ClarificationQuestion(
                    id="signedness",
                    field="ports.signed",
                    semantic_key="signedness",
                    question="Should comparisons use signed or unsigned interpretation?",
                    reason="Ordered comparisons can change behavior under signed versus unsigned interpretation.",
                    required=True,
                    choices=["signed", "unsigned"],
                    default=None,
                ),
                ClarificationQuestion(
                    id="opcode_mapping",
                    field="behavior.opcode_mapping",
                    semantic_key="opcode_mapping",
                    question="Please specify the mapping of the 2-bit op input.",
                    reason="Opcode mapping is required to avoid inventing control behavior.",
                    required=True,
                    choices=[],
                    default=None,
                ),
            ],
            assumptions=[],
        )

        pre_answer_merged = merge_with_local_ambiguity_policy(original_requirement, pre_answer_analysis)
        self.assertEqual(len(pre_answer_merged.clarification_questions), 1)
        self.assertEqual(pre_answer_merged.clarification_questions[0].semantic_key, "signedness")

        requirement = (
            "Create an 8-bit combinational module with 8-bit inputs a and b, a 2-bit input op, and outputs y, zero, "
            "and carry. When op is 0, y should equal a plus b. When op is 1, y should equal a minus b. When op is 2, "
            "y should equal a XOR b. When op is 3, output a if a is greater than b, otherwise output b. "
            "zero should be 1 when y is zero. carry should be the addition carry-out only when op is 0. "
            "Clarified requirements:\n- Signedness: unsigned"
        )
        analysis = RequirementAnalysis(
            ready=False,
            explicitly_specified=[],
            safely_inferred=[],
            missing_critical=["opcode_mapping"],
            ambiguous=["opcode_mapping"],
            clarification_questions=[
                ClarificationQuestion(
                    id="opcode_mapping",
                    field="behavior.opcode_mapping",
                    semantic_key="opcode_mapping",
                    question="Please specify the mapping of the 2-bit op input.",
                    reason="Opcode mapping is required to avoid inventing control behavior.",
                    required=True,
                    choices=[],
                    default=None,
                )
            ],
            assumptions=[],
        )

        merged = merge_with_local_ambiguity_policy(requirement, analysis)
        finalized = finalize_requirement_analysis_state(merged)
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.clarification_questions, [])
        self.assertEqual(finalized.missing_critical, [])
        self.assertIn("opcode_mapping", finalized.explicitly_specified)
        self.assertIn("signedness", finalized.explicitly_specified)

    def test_requirement_parse_result_rejects_needs_clarification_without_questions(self) -> None:
        with self.assertRaises(ValidationError):
            RequirementParseResult(
                requirement="Create a mux.",
                status=RequirementStatus.NEEDS_CLARIFICATION,
                hardware_spec=None,
                clarification_questions=[],
                unresolved_fields=[],
                assumptions=[],
                raw_model_output="{}",
                provider="test",
                model="test",
                attempts=1,
            )

    def test_finalize_requirement_analysis_state_promotes_ready_when_no_evidence_remains(self) -> None:
        analysis = RequirementAnalysis.model_construct(
            ready=False,
            explicitly_specified=[],
            safely_inferred=[],
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=[],
        )
        finalized = finalize_requirement_analysis_state(analysis)
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.clarification_questions, [])

    def test_finalize_requirement_analysis_state_raises_for_stale_unresolved_labels_without_questions(self) -> None:
        analysis = RequirementAnalysis(
            ready=False,
            missing_critical=["signedness"],
            ambiguous=["signedness"],
            clarification_questions=[],
            assumptions=[],
        )
        with self.assertRaises(AmbiguityPolicyInconsistencyError):
            finalize_requirement_analysis_state(analysis)

    def test_add_sub_ambiguity_is_resolved_by_executable_semantics(self) -> None:
        requirement = (
            "Create a 6-bit combinational module with 6-bit inputs a and b, a 1-bit input mode, and a 6-bit output y. "
            "When mode is 0, y should equal a plus b. When mode is 1, y should equal a minus b."
        )
        raw_analysis = RequirementAnalysis(
            ready=False,
            missing_critical=["signedness of inputs and output", "supported arithmetic operations"],
            ambiguous=["signedness of inputs and output", "supported arithmetic operations"],
            clarification_questions=[
                ClarificationQuestion(
                    id="alu_signedness",
                    field="ports.signed",
                    semantic_key="signedness",
                    question="Should arithmetic operations be signed or unsigned?",
                    reason="Signedness materially changes arithmetic behavior.",
                    required=True,
                    choices=["signed", "unsigned"],
                )
            ],
            assumptions=[],
        )
        merged = merge_with_local_ambiguity_policy(requirement, raw_analysis)
        finalized = finalize_requirement_analysis_state(merged)
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.missing_critical, [])
        self.assertEqual(finalized.clarification_questions, [])

    def test_add_sub_only_does_not_require_signedness_clarification(self) -> None:
        requirement = (
            "Create a 6-bit combinational module with 6-bit inputs a and b, a 1-bit input mode, and a 6-bit output y. "
            "When mode is 0, y should equal a plus b. When mode is 1, y should equal a minus b."
        )
        raw_analysis = RequirementAnalysis(
            ready=True,
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=[],
        )
        merged = merge_with_local_ambiguity_policy(requirement, raw_analysis)
        finalized = finalize_requirement_analysis_state(merged)
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.clarification_questions, [])

    def test_ordered_comparison_requires_signedness_clarification_when_unspecified(self) -> None:
        requirement = (
            "Create an 8-bit combinational module with 8-bit inputs a and b and an 8-bit output y. "
            "Output a if a is greater than b, otherwise output b."
        )
        raw_analysis = RequirementAnalysis(
            ready=True,
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=[],
        )
        merged = merge_with_local_ambiguity_policy(requirement, raw_analysis)
        self.assertFalse(merged.ready)
        question_keys = {question.semantic_key for question in merged.clarification_questions}
        self.assertIn("signedness", question_keys)
        signedness_question = next(question for question in merged.clarification_questions if question.semantic_key == "signedness")
        self.assertIn("a and b", signedness_question.question)

    def test_explicitly_unsigned_comparison_does_not_require_signedness_clarification(self) -> None:
        requirement = (
            "Create an 8-bit combinational module with unsigned 8-bit inputs a and b and an 8-bit output y. "
            "Output a if a is greater than b, otherwise output b."
        )
        raw_analysis = RequirementAnalysis(
            ready=True,
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=[],
        )
        merged = merge_with_local_ambiguity_policy(requirement, raw_analysis)
        finalized = finalize_requirement_analysis_state(merged)
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.clarification_questions, [])

    def test_explicitly_signed_comparison_does_not_require_signedness_clarification(self) -> None:
        requirement = (
            "Create a signed 8-bit combinational module with signed 8-bit inputs a and b and an 8-bit output y. "
            "Output a if a is greater than b, otherwise output b."
        )
        raw_analysis = RequirementAnalysis(
            ready=True,
            missing_critical=[],
            ambiguous=[],
            clarification_questions=[],
            assumptions=[],
        )
        merged = merge_with_local_ambiguity_policy(requirement, raw_analysis)
        finalized = finalize_requirement_analysis_state(merged)
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.clarification_questions, [])

    def test_missing_descriptive_hardware_intent_behavior_is_tolerated(self) -> None:
        payload = {
            "module_name": "simple_add",
            "design_type": "combinational",
            "ports": [
                {"name": "a", "direction": "input", "width": 4, "role": "data"},
                {"name": "b", "direction": "input", "width": 4, "role": "data"},
                {"name": "y", "direction": "output", "width": 4, "role": "data"},
            ],
            "combinational_intent": {
                "assignments": [
                    {
                        "target": "y",
                        "expression": {
                            "type": "binary",
                            "op": "ADD",
                            "left": {"type": "signal", "name": "a"},
                            "right": {"type": "signal", "name": "b"},
                        },
                    }
                ]
            },
        }
        normalized = normalize_hardware_intent_payload(payload)
        self.assertEqual(validate_hardware_intent_envelope(normalized), [])
        intent = HardwareIntent.model_validate(normalized)
        spec = compile_hardware_intent(intent)
        self.assertEqual(spec.behavior.description, "High-level behavior metadata omitted.")

    def test_missing_authoritative_combinational_intent_still_fails(self) -> None:
        payload = {
            "module_name": "missing_body",
            "design_type": "combinational",
            "ports": [
                {"name": "a", "direction": "input", "width": 4, "role": "data"},
                {"name": "y", "direction": "output", "width": 4, "role": "data"},
            ],
        }
        normalized = normalize_hardware_intent_payload(payload)
        errors = validate_hardware_intent_envelope(normalized)
        self.assertTrue(errors)
        self.assertIn("combinational_intent", errors[0])

    def test_verification_intent_envelope_guard_distinguishes_structure_from_schema(self) -> None:
        payload = {
            "schema_version": "2.0",
            "module_name": "bad_case_plan",
            "design_type": "combinational",
            "strategy": "deterministic",
            "cases": [
                {
                    "id": "BadCase",
                    "name": "bad case id",
                    "category": "FUNCTIONAL",
                    "target_behavior": "ADD",
                    "scenario": "ARITHMETIC",
                    "priority": 1,
                }
            ],
            "coverage_targets": [],
            "assumptions": [],
            "notes": [],
        }
        self.assertEqual(validate_verification_intent_envelope(payload), [])
        with self.assertRaises(ValidationError):
            VerificationIntentPlan.model_validate(payload)

    def test_scenario_cannot_use_semantic_feature_token(self) -> None:
        spec = build_priority_spec()
        intent = VerificationIntentPlan(
            module_name=spec.module_name,
            design_type=DesignType.COMBINATIONAL,
            strategy="deterministic",
            cases=[
                VerificationIntentCase(
                    id="valid_output_true",
                    name="NONZERO leaked into scenario",
                    category=TestCategory.FUNCTIONAL,
                    target_behavior="NONZERO",
                    scenario="NONZERO",
                    priority=1,
                    vector_hints={"data_in": 1},
                )
            ],
            coverage_targets=[],
            assumptions=[],
            notes=[],
        )
        with self.assertRaises(VerificationCompilationError) as ctx:
            compile_verification_intent_plan(spec, intent)
        self.assertEqual(ctx.exception.error_type, "INVALID_SCENARIO_VOCABULARY")

    def test_priority_mandatory_coverage_does_not_mutate_existing_ai_cases(self) -> None:
        spec = build_priority_spec()
        original_vectors = [128, 64, 160, 255, 0, 1]
        cases = [
            VerificationIntentCase(
                id="encode_highest_priority",
                name="highest one-hot",
                category=TestCategory.FUNCTIONAL,
                target_behavior="PRIORITY_SELECT",
                scenario="BOUNDARY",
                priority=1,
                vector_hints={"data_in": 128},
            ),
            VerificationIntentCase(
                id="encode_second_highest_priority",
                name="second highest one-hot",
                category=TestCategory.FUNCTIONAL,
                target_behavior="PRIORITY_SELECT",
                scenario="BOUNDARY",
                priority=1,
                vector_hints={"data_in": 64},
            ),
            VerificationIntentCase(
                id="encode_multiple_active_bits",
                name="multi-active priority competition",
                category=TestCategory.FUNCTIONAL,
                target_behavior="PRIORITY_SELECT",
                scenario="BASIC",
                priority=1,
                vector_hints={"data_in": 160},
            ),
            VerificationIntentCase(
                id="encode_all_bits_active",
                name="all bits active",
                category=TestCategory.FUNCTIONAL,
                target_behavior="PRIORITY_SELECT",
                scenario="BASIC",
                priority=1,
                vector_hints={"data_in": 255},
            ),
            VerificationIntentCase(
                id="encode_zero_input",
                name="zero input",
                category=TestCategory.FUNCTIONAL,
                target_behavior="PRIORITY_SELECT",
                scenario="BASIC",
                priority=1,
                vector_hints={"data_in": 0},
            ),
            VerificationIntentCase(
                id="check_valid_output",
                name="valid high",
                category=TestCategory.FUNCTIONAL,
                target_behavior="NONZERO",
                scenario="BASIC",
                priority=1,
                vector_hints={"data_in": 1},
            ),
        ]
        plan = VerificationIntentPlan(
            module_name=spec.module_name,
            design_type=DesignType.COMBINATIONAL,
            strategy="deterministic",
            cases=cases,
            coverage_targets=[],
            assumptions=[],
            notes=[],
        )
        compiled = compile_verification_intent_plan(spec, plan)
        preserved_vectors = [extract_input_vector(case)["data_in"] for case in compiled.cases[: len(original_vectors)]]
        self.assertEqual(preserved_vectors, original_vectors)
        self.assertEqual(len(compiled.cases), len(original_vectors))

    def test_priority_competition_detection_uses_actual_bit_population(self) -> None:
        self.assertTrue(is_priority_competition_vector({"data_in": 160}, "data_in", 8))
        self.assertFalse(is_priority_competition_vector({"data_in": 128}, "data_in", 8))

    def test_extract_input_vector_uses_assignment_payload(self) -> None:
        case = CompiledVerificationCase(
            id="simple_case",
            name="simple case",
            category=TestCategory.FUNCTIONAL,
            target_behavior="ADD",
            scenario="BASIC",
            priority=1,
            actions=[
                TestbenchAction(
                    type=TestbenchActionType.SET_INPUT,
                    assignment=InputAssignment(signal="a", value=5),
                )
            ],
            checks=[ExpectedCheck(signal="y", value=5)],
        )
        self.assertEqual(extract_input_vector(case), {"a": 5})

    def test_renderer_raises_structured_value_error_for_malformed_set_input_action(self) -> None:
        action = TestbenchAction.model_construct(type=TestbenchActionType.SET_INPUT, assignment=None, count=None)
        with self.assertRaisesRegex(ValueError, "requires assignment payload"):
            render_action(build_mux_spec(), action)

    def test_deterministic_expected_values_come_from_semantic_evaluator(self) -> None:
        spec = build_priority_spec()
        plan = VerificationIntentPlan(
            module_name=spec.module_name,
            design_type=DesignType.COMBINATIONAL,
            strategy="deterministic",
            cases=[
                VerificationIntentCase(
                    id="nonzero_bit0",
                    name="bit zero still asserts valid",
                    category=TestCategory.FUNCTIONAL,
                    target_behavior="NONZERO",
                    scenario="BASIC",
                    priority=1,
                    vector_hints={"data_in": 1},
                )
            ],
            coverage_targets=[],
            assumptions=[],
            notes=[],
        )
        compiled = compile_verification_intent_plan(spec, plan)
        checks_by_signal = {check.signal: check.value for check in compiled.cases[0].checks if check.value is not None}
        self.assertEqual(checks_by_signal["valid"], 1)
        self.assertEqual(checks_by_signal["encoded_out"], 0)

    def test_generic_combinational_fallback_preserves_valid_hints_and_improves_diversity(self) -> None:
        spec = build_add_sub_spec()
        plan = VerificationIntentPlan(
            module_name=spec.module_name,
            design_type=DesignType.COMBINATIONAL,
            strategy="deterministic",
            cases=[
                VerificationIntentCase(
                    id="add_zero",
                    name="add with partial invalid hint",
                    category=TestCategory.ARITHMETIC,
                    target_behavior="ADD",
                    scenario="ARITHMETIC",
                    priority=1,
                    vector_hints={"a": 16, "b": "-16"},
                    notes=["partial invalid hint case"],
                ),
                VerificationIntentCase(
                    id="add_max",
                    name="add max flavored case",
                    category=TestCategory.ARITHMETIC,
                    target_behavior="ADD",
                    scenario="BOUNDARY",
                    priority=1,
                    vector_hints={"mode": 0},
                ),
                VerificationIntentCase(
                    id="mode_add",
                    name="mode add explicit control",
                    category=TestCategory.CONTROL,
                    target_behavior="ADD",
                    scenario="BASIC",
                    priority=1,
                    vector_hints={"mode": 0},
                ),
                VerificationIntentCase(
                    id="sub_zero",
                    name="sub partial invalid hint",
                    category=TestCategory.ARITHMETIC,
                    target_behavior="SUB",
                    scenario="ARITHMETIC",
                    priority=1,
                    vector_hints={"a": 9, "b": "-1"},
                ),
                VerificationIntentCase(
                    id="mode_sub",
                    name="mode sub explicit control",
                    category=TestCategory.CONTROL,
                    target_behavior="SUB",
                    scenario="BASIC",
                    priority=1,
                    vector_hints={"mode": 1},
                ),
            ],
            coverage_targets=[],
            assumptions=[],
            notes=[],
        )

        compiled = compile_verification_intent_plan(spec, plan)
        compiled_vectors = {
            case.id: extract_input_vector(case)
            for case in compiled.cases[: len(plan.cases)]
        }

        self.assertEqual(compiled_vectors["add_zero"]["a"], 16)
        self.assertEqual(compiled_vectors["add_zero"]["mode"], 0)
        self.assertEqual(compiled_vectors["sub_zero"]["a"], 9)
        self.assertEqual(compiled_vectors["sub_zero"]["mode"], 1)

        add_vectors = {
            tuple(sorted(compiled_vectors[case_id].items()))
            for case_id in ("add_zero", "add_max", "mode_add")
        }
        sub_vectors = {
            tuple(sorted(compiled_vectors[case_id].items()))
            for case_id in ("sub_zero", "mode_sub")
        }
        self.assertGreater(len(add_vectors), 1)
        self.assertGreater(len(sub_vectors), 1)

        add_zero_case = next(case for case in compiled.cases if case.id == "add_zero")
        sub_zero_case = next(case for case in compiled.cases if case.id == "sub_zero")
        self.assertTrue(any("ignored invalid AI vector hint b=-16" in note for note in add_zero_case.compilation_notes))
        self.assertTrue(any("ignored invalid AI vector hint b=-1" in note for note in sub_zero_case.compilation_notes))

        add_zero_checks = {check.signal: check.value for check in add_zero_case.checks if check.value is not None}
        add_zero_expected = evaluate_combinational_semantics(spec, spec.semantics.combinational, compiled_vectors["add_zero"])
        self.assertEqual(add_zero_checks["y"], add_zero_expected["y"])

    def test_supported_semantic_fixtures_evaluate_deterministically(self) -> None:
        fixtures = [
            (build_mux_spec(), {"a": 1, "b": 0, "sel": 0}, {"y": 1}),
            (build_add_sub_spec(), {"a": 5, "b": 3, "mode": 0}, {"y": 8}),
            (build_comparator_spec(), {"a": 2, "b": 1}, {"eq": 0, "gt": 1, "lt": 0}),
            (build_add_xor_spec(), {"a": 0b1010, "b": 0b0110, "sel": 1}, {"y": 0b1100}),
            (build_priority_spec(), {"data_in": 0b10100000}, {"encoded_out": 7, "valid": 1}),
            (build_bitselect_spec(), {"data_in": 0b0100, "invert": 1}, {"y": 0}),
            (build_decoder_spec(), {"sel": 2}, {"y": 0b0100}),
        ]
        for spec, inputs, expected in fixtures:
            with self.subTest(module=spec.module_name):
                self.assertIsNotNone(spec.semantics)
                actual = evaluate_combinational_semantics(spec, spec.semantics.combinational, inputs)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
class HardwareIntentExpressivenessTests(unittest.TestCase):
    def _signal(self, name: str, direction: str, width: int, signed: bool = False):
        from rtl_assistant.models.hardware_spec import PortSpec

        return PortSpec(name=name, direction=direction, width=width, signed=signed)

    def _selector_intent(self):
        from rtl_assistant.models.hardware_intent import (
            CombinationalHardwareIntent,
            HardwareIntent,
            IntentAssignment,
            IntentBinaryExpr,
            IntentBinaryOp,
            IntentCaseSelectCase,
            IntentCaseSelectExpr,
            IntentConditionalExpr,
            IntentLiteralExpr,
            IntentSignalExpr,
        )

        return HardwareIntent(
            module_name="selector_core",
            design_type="combinational",
            ports=[
                self._signal("a", "input", 8),
                self._signal("b", "input", 8),
                self._signal("op", "input", 2),
                self._signal("y", "output", 8),
                self._signal("zero", "output", 1),
            ],
            combinational_intent=CombinationalHardwareIntent(
                assignments=[
                    IntentAssignment(
                        target="y",
                        expression=IntentCaseSelectExpr(
                            selector=IntentSignalExpr(name="op"),
                            cases=[
                                IntentCaseSelectCase(
                                    value=0,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.ADD,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=1,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.SUB,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=2,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.BIT_XOR,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=3,
                                    expression=IntentConditionalExpr(
                                        condition=IntentBinaryExpr(
                                            op=IntentBinaryOp.GT,
                                            left=IntentSignalExpr(name="a"),
                                            right=IntentSignalExpr(name="b"),
                                        ),
                                        when_true=IntentSignalExpr(name="a"),
                                        when_false=IntentSignalExpr(name="b"),
                                    ),
                                ),
                            ],
                            default_expression=IntentLiteralExpr(value=0, width=8),
                        ),
                    ),
                    IntentAssignment(
                        target="zero",
                        expression=IntentBinaryExpr(
                            op=IntentBinaryOp.EQ,
                            left=IntentSignalExpr(name="y"),
                            right=IntentLiteralExpr(value=0, width=8),
                        ),
                    ),
                ]
            ),
        )

    def _carry_intent(self):
        from rtl_assistant.models.hardware_intent import (
            CombinationalHardwareIntent,
            HardwareIntent,
            IntentAssignment,
            IntentBinaryExpr,
            IntentBinaryOp,
            IntentBitSelectExpr,
            IntentCaseSelectCase,
            IntentCaseSelectExpr,
            IntentExtendExpr,
            IntentExtendMode,
            IntentLiteralExpr,
            IntentSignalExpr,
        )

        extended_sum = IntentBinaryExpr(
            op=IntentBinaryOp.ADD,
            left=IntentExtendExpr(
                operand=IntentSignalExpr(name="a"),
                target_width=9,
                mode=IntentExtendMode.ZERO_EXTEND,
            ),
            right=IntentExtendExpr(
                operand=IntentSignalExpr(name="b"),
                target_width=9,
                mode=IntentExtendMode.ZERO_EXTEND,
            ),
        )

        return HardwareIntent(
            module_name="carry_core",
            design_type="combinational",
            ports=[
                self._signal("a", "input", 8),
                self._signal("b", "input", 8),
                self._signal("op", "input", 1),
                self._signal("y", "output", 8),
                self._signal("carry", "output", 1),
            ],
            combinational_intent=CombinationalHardwareIntent(
                assignments=[
                    IntentAssignment(
                        target="y",
                        expression=IntentCaseSelectExpr(
                            selector=IntentSignalExpr(name="op"),
                            cases=[
                                IntentCaseSelectCase(
                                    value=0,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.ADD,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=1,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.BIT_XOR,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                            ],
                            default_expression=IntentLiteralExpr(value=0, width=8),
                        ),
                    ),
                    IntentAssignment(
                        target="carry",
                        expression=IntentCaseSelectExpr(
                            selector=IntentSignalExpr(name="op"),
                            cases=[
                                IntentCaseSelectCase(
                                    value=0,
                                    expression=IntentBitSelectExpr(signal=extended_sum, index=8),
                                ),
                            ],
                            default_expression=IntentLiteralExpr(value=0, width=1),
                        ),
                    ),
                ]
            ),
        )

    def _conditional_carry_intent(self):
        from rtl_assistant.models.hardware_intent import (
            CombinationalHardwareIntent,
            HardwareIntent,
            IntentAssignment,
            IntentBinaryExpr,
            IntentBinaryOp,
            IntentBitSelectExpr,
            IntentCaseSelectCase,
            IntentCaseSelectExpr,
            IntentConditionalExpr,
            IntentExtendExpr,
            IntentExtendMode,
            IntentLiteralExpr,
            IntentSignalExpr,
        )

        extended_sum = IntentBinaryExpr(
            op=IntentBinaryOp.ADD,
            left=IntentExtendExpr(
                operand=IntentSignalExpr(name="a"),
                target_width=9,
                mode=IntentExtendMode.ZERO_EXTEND,
            ),
            right=IntentExtendExpr(
                operand=IntentSignalExpr(name="b"),
                target_width=9,
                mode=IntentExtendMode.ZERO_EXTEND,
            ),
        )

        return HardwareIntent(
            module_name="conditional_carry_core",
            design_type="combinational",
            ports=[
                self._signal("a", "input", 8),
                self._signal("b", "input", 8),
                self._signal("op", "input", 2),
                self._signal("y", "output", 8),
                self._signal("carry", "output", 1),
            ],
            combinational_intent=CombinationalHardwareIntent(
                assignments=[
                    IntentAssignment(
                        target="y",
                        expression=IntentCaseSelectExpr(
                            selector=IntentSignalExpr(name="op"),
                            cases=[
                                IntentCaseSelectCase(
                                    value=0,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.ADD,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=1,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.SUB,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=2,
                                    expression=IntentBinaryExpr(
                                        op=IntentBinaryOp.BIT_XOR,
                                        left=IntentSignalExpr(name="a"),
                                        right=IntentSignalExpr(name="b"),
                                    ),
                                ),
                                IntentCaseSelectCase(
                                    value=3,
                                    expression=IntentConditionalExpr(
                                        condition=IntentBinaryExpr(
                                            op=IntentBinaryOp.GT,
                                            left=IntentSignalExpr(name="a"),
                                            right=IntentSignalExpr(name="b"),
                                        ),
                                        when_true=IntentSignalExpr(name="a"),
                                        when_false=IntentSignalExpr(name="b"),
                                    ),
                                ),
                            ],
                            default_expression=IntentLiteralExpr(value=0, width=8),
                        ),
                    ),
                    IntentAssignment(
                        target="carry",
                        expression=IntentConditionalExpr(
                            condition=IntentBinaryExpr(
                                op=IntentBinaryOp.EQ,
                                left=IntentSignalExpr(name="op"),
                                right=IntentLiteralExpr(value=0, width=2),
                            ),
                            when_true=IntentBitSelectExpr(signal=extended_sum, index=8),
                            when_false=IntentLiteralExpr(value=0, width=1),
                        ),
                    ),
                ]
            ),
        )

    def test_case_select_compiles_and_evaluates_multiple_branches(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        spec = compile_hardware_intent(self._selector_intent())
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 5, "b": 7, "op": 0})
        self.assertEqual(result["y"], 12)
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 7, "b": 5, "op": 1})
        self.assertEqual(result["y"], 2)
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 7, "b": 5, "op": 2})
        self.assertEqual(result["y"], 2)
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 7, "b": 5, "op": 3})
        self.assertEqual(result["y"], 7)

    def test_zero_flag_can_depend_on_compiled_output_expression(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        spec = compile_hardware_intent(self._selector_intent())
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 1, "b": 1, "op": 2})
        self.assertEqual(result["y"], 0)
        self.assertEqual(result["zero"], 1)

    def test_carry_out_is_representable_via_width_extension_and_bit_select(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        spec = compile_hardware_intent(self._carry_intent())
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 255, "b": 1, "op": 0})
        self.assertEqual(result["y"], 0)
        self.assertEqual(result["carry"], 1)

    def test_non_overflow_add_keeps_carry_low(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        spec = compile_hardware_intent(self._carry_intent())
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 5, "b": 7, "op": 0})
        self.assertEqual(result["carry"], 0)

    def test_non_add_case_forces_carry_to_default(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        spec = compile_hardware_intent(self._carry_intent())
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 255, "b": 1, "op": 1})
        self.assertEqual(result["carry"], 0)

    def test_conditional_carry_nested_inputs_compile_and_evaluate(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        spec = compile_hardware_intent(self._conditional_carry_intent())
        overflow = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 255, "b": 1, "op": 0})
        self.assertEqual(overflow["carry"], 1)
        no_overflow = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"a": 5, "b": 7, "op": 0})
        self.assertEqual(no_overflow["carry"], 0)

    def test_case_select_duplicate_values_are_rejected(self):
        from pydantic import ValidationError
        from rtl_assistant.models.hardware_intent import IntentCaseSelectCase, IntentCaseSelectExpr, IntentLiteralExpr, IntentSignalExpr

        with self.assertRaises(ValidationError):
            IntentCaseSelectExpr(
                selector=IntentSignalExpr(name="op"),
                cases=[
                    IntentCaseSelectCase(value=0, expression=IntentLiteralExpr(value=0, width=2)),
                    IntentCaseSelectCase(value=0, expression=IntentLiteralExpr(value=1, width=2)),
                ],
                default_expression=IntentLiteralExpr(value=0, width=2),
            )

    def test_width_extension_supports_explicit_growth(self):
        from rtl_assistant.models.semantics import BinarySemanticOp
        from rtl_assistant.semantics.evaluator import EvaluatedValue, evaluate_binary_expr

        result = evaluate_binary_expr(
            op=BinarySemanticOp.ADD,
            left=EvaluatedValue(0xFF, 9, False),
            right=EvaluatedValue(1, 9, False),
        )
        self.assertEqual(result.value, 0x100)

    def test_semantic_validator_rejects_output_dependency_cycles(self):
        from pydantic import ValidationError
        from rtl_assistant.models.hardware_spec import BehaviorSpec, HardwareSpec
        from rtl_assistant.models.semantics import (
            BinaryExpr,
            BinarySemanticOp,
            CombinationalSemantics,
            HardwareSemantics,
            LiteralExpr,
            SemanticAssignment,
            SignalExpr,
        )
        spec_payload = {
            "module_name": "cycle_demo",
            "design_type": "combinational",
            "ports": [self._signal("a", "output", 1), self._signal("b", "output", 1)],
            "behavior": BehaviorSpec(),
            "semantics": HardwareSemantics(
                combinational=CombinationalSemantics(
                    assignments=[
                        SemanticAssignment(
                            target="a",
                            expression=BinaryExpr(
                                op=BinarySemanticOp.EQ,
                                left=SignalExpr(name="b"),
                                right=LiteralExpr(value=0, width=1),
                            ),
                        ),
                        SemanticAssignment(
                            target="b",
                            expression=BinaryExpr(
                                op=BinarySemanticOp.EQ,
                                left=SignalExpr(name="a"),
                                right=LiteralExpr(value=0, width=1),
                            ),
                        ),
                    ]
                )
            ),
        }

        with self.assertRaises(ValidationError) as error_context:
            HardwareSpec(**spec_payload)
        self.assertIn("SEMANTIC_CYCLE", str(error_context.exception))

    def test_highest_index_priority_select_prefers_highest_active_bit(self):
        from rtl_assistant.hardware_intent.compiler import compile_hardware_intent
        from rtl_assistant.models.hardware_intent import (
            CombinationalHardwareIntent,
            HardwareIntent,
            IntentAssignment,
            IntentPrioritySelectExpr,
            IntentSignalExpr,
            IntentUnaryExpr,
            IntentUnaryOp,
            PriorityDirection,
        )
        from rtl_assistant.semantics.evaluator import evaluate_combinational_semantics

        intent = HardwareIntent(
            module_name="priority_high_demo",
            design_type="combinational",
            ports=[
                self._signal("data_in", "input", 8),
                self._signal("encoded_out", "output", 3),
                self._signal("valid", "output", 1),
            ],
            combinational_intent=CombinationalHardwareIntent(
                assignments=[
                    IntentAssignment(
                        target="encoded_out",
                        expression=IntentPrioritySelectExpr(
                            source_signal="data_in",
                            direction=PriorityDirection.HIGHEST_INDEX_FIRST,
                        ),
                    ),
                    IntentAssignment(
                        target="valid",
                        expression=IntentUnaryExpr(
                            op=IntentUnaryOp.NONZERO,
                            operand=IntentSignalExpr(name="data_in"),
                        ),
                    ),
                ]
            ),
        )

        spec = compile_hardware_intent(intent)
        result = evaluate_combinational_semantics(spec, spec.semantics.combinational, {"data_in": 0b10100000})
        self.assertEqual(result["encoded_out"], 7)
        self.assertEqual(result["valid"], 1)
class ClarificationFilteringRegressionTests(__import__("unittest").TestCase):
    def test_explicit_behavior_and_selector_dispatch_only_require_signedness(self):
        from rtl_assistant.models.llm import (
            ClarificationQuestion,
            RequirementAnalysis,
        )
        from rtl_assistant.spec.ai_parser import (
            finalize_requirement_analysis_state,
            merge_with_local_ambiguity_policy,
        )

        requirement = (
            "Create an 8-bit combinational module with 8-bit inputs a and b, "
            "a 2-bit input op, an 8-bit output y, and 1-bit outputs zero and carry. "
            "When op is 0, y should equal a plus b. "
            "When op is 1, y should equal a minus b. "
            "When op is 2, y should equal a XOR b. "
            "When op is 3, output a if a is greater than b, otherwise output b. "
            "zero should be 1 when y is zero. "
            "carry should be the addition carry-out when op is 0, and 0 otherwise."
        )

        analysis = RequirementAnalysis(
            ready=False,
            explicitly_specified=[],
            safely_inferred=[],
            missing_critical=[
                "signedness",
                "carry_behavior",
                "opcode_mapping",
                "mux_input_count",
            ],
            ambiguous=[
                "signedness",
                "carry_behavior",
                "opcode_mapping",
                "mux_input_count",
            ],
            clarification_questions=[
                ClarificationQuestion(
                    id="signedness",
                    field="signedness",
                    semantic_key="signedness",
                    question="Should comparisons use signed or unsigned interpretation?",
                    reason="Greater-than behavior depends on signedness.",
                    choices=["signed", "unsigned"],
                    required=True,
                ),
                ClarificationQuestion(
                    id="carry_behavior",
                    field="carry_behavior",
                    semantic_key="carry_behavior",
                    question="Should carry represent addition carry-out for op=0 and 0 otherwise?",
                    reason="carry output behavior may be ambiguous.",
                    choices=["Yes"],
                    required=True,
                ),
                ClarificationQuestion(
                    id="opcode_mapping",
                    field="opcode_mapping",
                    semantic_key="opcode_mapping",
                    question="Please specify the mapping of the 2-bit op input.",
                    reason="Selector dispatch appears ambiguous.",
                    required=True,
                ),
                ClarificationQuestion(
                    id="mux_input_count",
                    field="mux_input_count",
                    semantic_key="mux_input_count",
                    question="How many inputs should the mux have?",
                    reason="The operation of selecting between two outputs based on the op input requires a mux.",
                    required=True,
                ),
            ],
            assumptions=[],
        )

        merged = merge_with_local_ambiguity_policy(requirement, analysis)
        self.assertEqual(len(merged.clarification_questions), 1)
        self.assertEqual(merged.clarification_questions[0].semantic_key, "signedness")

        enriched = requirement + "\n\nClarified requirements:\n- Signedness: unsigned"
        post_answer = RequirementAnalysis(
            ready=False,
            explicitly_specified=[],
            safely_inferred=[],
            missing_critical=["carry_behavior", "opcode_mapping", "mux_input_count"],
            ambiguous=["carry_behavior", "opcode_mapping", "mux_input_count"],
            clarification_questions=[
                ClarificationQuestion(
                    id="carry_behavior",
                    field="carry_behavior",
                    semantic_key="carry_behavior",
                    question="Should carry represent addition carry-out for op=0 and 0 otherwise?",
                    reason="carry output behavior may be ambiguous.",
                    required=True,
                ),
                ClarificationQuestion(
                    id="opcode_mapping",
                    field="opcode_mapping",
                    semantic_key="opcode_mapping",
                    question="Please specify the mapping of the 2-bit op input.",
                    reason="Selector dispatch appears ambiguous.",
                    required=True,
                ),
                ClarificationQuestion(
                    id="mux_input_count",
                    field="mux_input_count",
                    semantic_key="mux_input_count",
                    question="How many inputs should the mux have?",
                    reason="The operation of selecting between two outputs based on the op input requires a mux.",
                    required=True,
                ),
            ],
            assumptions=[],
        )

        finalized = finalize_requirement_analysis_state(
            merge_with_local_ambiguity_policy(enriched, post_answer)
        )
        self.assertTrue(finalized.ready)
        self.assertEqual(finalized.clarification_questions, [])
import unittest
