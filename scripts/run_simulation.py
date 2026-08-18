import argparse
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.hardware_tools.iverilog import run_simulation
from rtl_assistant.models.simulation import FinalStatus, SimulationReport


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Generic SystemVerilog simulation runner.")
    parser.add_argument("--rtl", required=True, help="Path to the RTL module file.")
    parser.add_argument("--testbench", required=True, help="Path to the testbench file.")
    parser.add_argument("--output", help="Path to the output compiled simulation file (optional).")
    parser.add_argument("--report", help="Path to save the structured JSON report (optional).")
    return parser.parse_args()


def write_json_report(report_path_str: str, report: SimulationReport) -> None:
    """Serialize and save the simulation report to JSON."""

    report_path = Path(report_path_str)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"JSON report saved to: {report_path.resolve()}")


def print_simulation_report(report: SimulationReport) -> None:
    """Print user-facing simulation results while preserving existing semantics."""

    if report.error_type == "RTL_FILE_NOT_FOUND":
        print(f"ERROR: {report.error_message}", file=sys.stderr)
        return

    if report.error_type == "TESTBENCH_FILE_NOT_FOUND":
        print(f"ERROR: {report.error_message}", file=sys.stderr)
        return

    print("Compiling design...")
    if report.compile_passed:
        print("Compilation successful")
    else:
        print("COMPILATION FAILED", file=sys.stderr)
        if report.compile_stdout:
            print(report.compile_stdout, end="")
        if report.compile_stderr:
            print(report.compile_stderr, end="", file=sys.stderr)
        if report.error_message:
            print(report.error_message, file=sys.stderr)
        return

    print("Running simulation...")
    if report.simulation_stdout:
        print(report.simulation_stdout, end="")
    if report.simulation_stderr:
        print(report.simulation_stderr, end="", file=sys.stderr)

    if report.final_status == FinalStatus.FAIL and report.error_message:
        print(f"ERROR: {report.error_message}", file=sys.stderr)

    print(f"FINAL RESULT: {report.final_status.value}")
    if report.final_status == FinalStatus.UNKNOWN:
        print(
            "The testbench did not print a recognizable pass or fail marker "
            "(e.g., 'PASS', 'PASSED', 'FAIL', or 'FAILED')."
        )


def status_to_exit_code(status: FinalStatus) -> int:
    """Map final status to process exit code."""

    if status == FinalStatus.PASS:
        return 0
    if status == FinalStatus.FAIL:
        return 1
    return 2


def main() -> int:
    args = parse_arguments()
    report = run_simulation(
        rtl_path=args.rtl,
        testbench_path=args.testbench,
        output_path=args.output,
        base_dir=repository_root,
    )

    print_simulation_report(report)

    if args.report:
        try:
            write_json_report(args.report, report)
        except Exception as exc:
            print("INTERNAL ERROR: Report validation or generation failed!", file=sys.stderr)
            print(f"Error details:\n{exc}", file=sys.stderr)
            return 1

    return status_to_exit_code(report.final_status)


if __name__ == "__main__":
    sys.exit(main())
