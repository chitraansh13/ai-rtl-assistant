import argparse
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.models.simulation import FinalStatus
from rtl_assistant.models.verification import VerificationReport, VerificationStatus
from rtl_assistant.pipeline.verification import verify_rtl


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for the unified verification CLI."""

    parser = argparse.ArgumentParser(description="Unified RTL verification runner.")
    parser.add_argument("--rtl", required=True, help="Path to the RTL module file.")
    parser.add_argument("--testbench", required=True, help="Path to the testbench file.")
    parser.add_argument("--top", required=True, help="Name of the top module.")
    parser.add_argument("--report", help="Path to save the structured JSON verification report (optional).")
    return parser.parse_args()


def write_json_report(report_path_str: str, report: VerificationReport) -> None:
    """Serialize and save the unified verification report to a JSON file."""

    report_path = Path(report_path_str)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"JSON verification report saved to: {report_path.resolve()}")


def print_summary(report: VerificationReport) -> None:
    """Print a concise unified verification summary."""

    print("\n========================================")
    print("RTL Verification")
    print("========================================")
    print(f"Lint:       {report.lint.status.value}")
    print(f"Simulation: {report.simulation.final_status.value}")
    print(f"Synthesis:  {report.synthesis.status.value}")
    print("")
    print(f"Overall:    {report.overall_status.value}")
    print("========================================")

    if report.lint.error_type or report.lint.errors:
        print("\nLint Details:")
        if report.lint.error_type:
            print(f"  Type:    {report.lint.error_type}")
            print(f"  Message: {report.lint.error_message}")
        for error in report.lint.errors[:5]:
            print(f"  {error}")

    if report.simulation.error_type or report.simulation.final_status != FinalStatus.PASS:
        print("\nSimulation Details:")
        if report.simulation.error_type:
            print(f"  Type:    {report.simulation.error_type}")
            print(f"  Message: {report.simulation.error_message}")
        elif report.simulation.final_status == FinalStatus.UNKNOWN:
            print("  Simulation completed without a recognizable PASS/FAIL marker.")

    if report.synthesis.error_type or report.synthesis.errors:
        print("\nSynthesis Details:")
        if report.synthesis.error_type:
            print(f"  Type:    {report.synthesis.error_type}")
            print(f"  Message: {report.synthesis.error_message}")
        for error in report.synthesis.errors[:5]:
            print(f"  {error}")


def status_to_exit_code(status: VerificationStatus) -> int:
    """Map unified verification status to process exit code."""

    if status == VerificationStatus.PASS:
        return 0
    if status == VerificationStatus.FAIL:
        return 1
    return 2


def main() -> int:
    args = parse_arguments()
    report = verify_rtl(args.rtl, args.testbench, args.top)
    print_summary(report)

    if args.report:
        try:
            write_json_report(args.report, report)
        except Exception as exc:
            print(f"INTERNAL ERROR: Failed to write JSON report: {exc}", file=sys.stderr)
            return 1

    return status_to_exit_code(report.overall_status)


if __name__ == "__main__":
    sys.exit(main())
