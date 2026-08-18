import time
from pathlib import Path

from rtl_assistant.hardware_tools import run_simulation, run_verilator_lint, run_yosys_synthesis
from rtl_assistant.models.lint import LintStatus
from rtl_assistant.models.simulation import FinalStatus
from rtl_assistant.models.synthesis import SynthesisStatus
from rtl_assistant.models.verification import VerificationReport, VerificationStatus


def determine_overall_status(
    lint_status: LintStatus,
    simulation_status: FinalStatus,
    synthesis_status: SynthesisStatus,
) -> VerificationStatus:
    """Determine the overall status from stage results."""

    if (
        lint_status == LintStatus.FAIL
        or simulation_status == FinalStatus.FAIL
        or synthesis_status == SynthesisStatus.FAIL
    ):
        return VerificationStatus.FAIL

    if (
        lint_status == LintStatus.PASS
        and simulation_status == FinalStatus.PASS
        and synthesis_status == SynthesisStatus.PASS
    ):
        return VerificationStatus.PASS

    return VerificationStatus.UNKNOWN


def verify_rtl(
    rtl_path: str | Path,
    testbench_path: str | Path,
    top_module: str,
) -> VerificationReport:
    """Run lint, simulation, and synthesis for an RTL module and return a unified report."""

    start_time = time.perf_counter()
    lint_report = run_verilator_lint(rtl_path)
    simulation_report = run_simulation(rtl_path, testbench_path)
    synthesis_report = run_yosys_synthesis(rtl_path, top_module)
    total_duration_ms = int((time.perf_counter() - start_time) * 1000)

    overall_status = determine_overall_status(
        lint_report.status,
        simulation_report.final_status,
        synthesis_report.status,
    )

    return VerificationReport(
        rtl_file=str(Path(rtl_path).resolve()),
        testbench_file=str(Path(testbench_path).resolve()),
        top_module=top_module,
        overall_status=overall_status,
        lint=lint_report,
        simulation=simulation_report,
        synthesis=synthesis_report,
        total_duration_ms=total_duration_ms,
    )
