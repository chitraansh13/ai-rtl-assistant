from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.testbench.ir import (
    ExpectedCheck,
    TestbenchAction,
    TestbenchActionType,
    TestbenchCase,
    TestbenchPlan,
)


def render_testbench(
    hardware_spec: HardwareSpec,
    testbench_plan: TestbenchPlan,
) -> str:
    """Render deterministic SystemVerilog testbench text from a structured IR."""

    lines: list[str] = []
    tb_module_name = f"{hardware_spec.module_name}_tb"

    lines.append(f"module {tb_module_name};")
    lines.append("")
    lines.extend(render_signal_declarations(hardware_spec))
    lines.append("integer failed_tests;")
    lines.append("")
    lines.extend(render_dut_instantiation(hardware_spec))

    if hardware_spec.clock is not None:
        lines.append("")
        lines.extend(render_clock_process(hardware_spec))

    lines.append("")
    lines.extend(render_main_sequence(hardware_spec, testbench_plan))
    lines.append("")
    lines.append("endmodule")
    return "\n".join(lines)


def render_signal_declarations(hardware_spec: HardwareSpec) -> list[str]:
    """Render DUT-facing signal declarations derived directly from HardwareSpec."""

    declarations: list[str] = []
    for port in hardware_spec.ports:
        declarations.append(f"{render_logic_declaration(port.name, port.width)}")
    return declarations


def render_logic_declaration(signal_name: str, width: int) -> str:
    """Render one width-aware logic declaration."""

    if width == 1:
        return f"logic {signal_name};"
    return f"logic [{width - 1}:0] {signal_name};"


def render_dut_instantiation(hardware_spec: HardwareSpec) -> list[str]:
    """Render named DUT instantiation from HardwareSpec ports."""

    lines = [f"{hardware_spec.module_name} dut ("]
    port_mappings = [f"    .{port.name}({port.name})" for port in hardware_spec.ports]
    for index, mapping in enumerate(port_mappings):
        suffix = "," if index < len(port_mappings) - 1 else ""
        lines.append(f"{mapping}{suffix}")
    lines.append(");")
    return lines


def render_clock_process(hardware_spec: HardwareSpec) -> list[str]:
    """Render a simple deterministic clock generator for sequential DUTs."""

    assert hardware_spec.clock is not None
    clock_name = hardware_spec.clock.signal
    return [
        "initial begin",
        f"    {clock_name} = 1'b0;",
        f"    forever #5 {clock_name} = ~{clock_name};",
        "end",
    ]


def render_main_sequence(
    hardware_spec: HardwareSpec,
    testbench_plan: TestbenchPlan,
) -> list[str]:
    """Render the main deterministic stimulus and checking sequence."""

    lines = ["initial begin"]
    lines.extend(indent_lines(render_initialization(hardware_spec), 1))

    for test_case in testbench_plan.tests:
        lines.append("")
        lines.extend(indent_lines(render_test_case(hardware_spec, test_case), 1))

    lines.append("")
    lines.append("    if (failed_tests == 0)")
    lines.append('        $display("ALL TESTS PASSED");')
    lines.append("    else")
    lines.append('        $display("Failed tests: %0d", failed_tests);')
    lines.append("")
    lines.append("    $finish;")
    lines.append("end")
    return lines


def render_initialization(hardware_spec: HardwareSpec) -> list[str]:
    """Render deterministic initial values for helper state and DUT inputs."""

    lines = ["failed_tests = 0;"]
    for port in hardware_spec.ports:
        if port.direction.value != "input":
            continue
        if hardware_spec.clock is not None and port.name == hardware_spec.clock.signal:
            continue
        initial_value = 0
        if hardware_spec.reset is not None and port.name == hardware_spec.reset.signal:
            initial_value = inactive_reset_value(hardware_spec)
        lines.append(f"{port.name} = {render_sv_literal(port.width, initial_value)};")
    return lines


def render_test_case(
    hardware_spec: HardwareSpec,
    test_case: TestbenchCase,
) -> list[str]:
    """Render one inline test section with exact planned checks."""

    lines = [
        f"// test_id: {test_case.id}",
        f'$display("RUN: {test_case.id}");',
    ]
    for action in test_case.actions:
        lines.extend(render_action(hardware_spec, action))

    lines.extend(render_inline_check(hardware_spec, test_case))
    return lines


def render_action(hardware_spec: HardwareSpec, action: TestbenchAction) -> list[str]:
    """Render one deterministic action."""

    if action.type == TestbenchActionType.SET_INPUT:
        assert action.assignment is not None
        port_width = find_port_width(hardware_spec, action.assignment.signal)
        if port_width is None:
            raise ValueError(f"Unknown input signal during render: {action.assignment.signal}")
        return [f"{action.assignment.signal} = {render_sv_literal(port_width, action.assignment.value)};"]

    if action.type == TestbenchActionType.ACTIVE_CLOCK_EDGE:
        assert hardware_spec.clock is not None
        edge_keyword = "posedge" if hardware_spec.clock.edge.value == "positive" else "negedge"
        return [f"@({edge_keyword} {hardware_spec.clock.signal});", "#1;"]

    if action.type == TestbenchActionType.REPEAT_ACTIVE_EDGES:
        assert hardware_spec.clock is not None
        assert action.count is not None
        edge_keyword = "posedge" if hardware_spec.clock.edge.value == "positive" else "negedge"
        return [
            f"repeat ({action.count}) begin",
            f"    @({edge_keyword} {hardware_spec.clock.signal});",
            "    #1;",
            "end",
        ]

    if action.type == TestbenchActionType.SETTLE:
        return ["#1;"]

    raise ValueError(f"Unsupported action type during render: {action.type}")


def render_inline_check(
    hardware_spec: HardwareSpec,
    test_case: TestbenchCase,
) -> list[str]:
    """Render one inline mismatch predicate and PASS/FAIL reporting block."""

    mismatch_lines = [render_mismatch_predicate(hardware_spec, check) for check in test_case.checks]
    lines = ["if ("]
    for index, predicate in enumerate(mismatch_lines):
        suffix = " ||" if index < len(mismatch_lines) - 1 else ""
        lines.append(f"    {predicate}{suffix}")
    lines.append(") begin")
    lines.append(f'    $display("FAIL: {test_case.id}");')
    lines.append("    failed_tests++;")
    lines.append("end else begin")
    lines.append(f'    $display("PASS: {test_case.id}");')
    lines.append("end")
    return lines


def render_mismatch_predicate(hardware_spec: HardwareSpec, check: ExpectedCheck) -> str:
    """Render one exact output-mismatch predicate."""

    actual_width = find_port_width(hardware_spec, check.signal)
    if actual_width is None:
        raise ValueError(f"Unknown output signal during render: {check.signal}")

    if check.reference_signal is not None:
        reference_width = find_port_width(hardware_spec, check.reference_signal)
        if reference_width is None:
            raise ValueError(f"Unknown reference signal during render: {check.reference_signal}")
        if reference_width != actual_width:
            raise ValueError(
                f"Signal-equality check width mismatch: {check.signal} is {actual_width} bits but {check.reference_signal} is {reference_width} bits"
            )
        return f"{check.signal} !== {check.reference_signal}"

    assert check.value is not None
    return f"{check.signal} !== {render_sv_literal(actual_width, check.value)}"


def render_sv_literal(width: int, value: int) -> str:
    """Render one width-aware SystemVerilog binary literal."""

    if width < 1:
        raise ValueError("Literal width must be at least 1")
    if value < 0:
        raise ValueError("Literal value must be non-negative")

    mask = (1 << width) - 1
    if value > mask:
        raise ValueError(f"Value {value} does not fit in {width} bits")
    return f"{width}'b{format(value, f'0{width}b')}"


def find_port_width(hardware_spec: HardwareSpec, signal_name: str) -> int | None:
    """Return the width of one named port."""

    for port in hardware_spec.ports:
        if port.name == signal_name:
            return port.width
    return None


def inactive_reset_value(hardware_spec: HardwareSpec) -> int:
    """Return the reset signal's inactive value from HardwareSpec polarity."""

    assert hardware_spec.reset is not None
    return 0 if hardware_spec.reset.polarity.value == "active_high" else 1


def indent_lines(lines: list[str], depth: int) -> list[str]:
    """Indent one list of rendered lines."""

    prefix = "    " * depth
    return [f"{prefix}{line}" if line else "" for line in lines]
