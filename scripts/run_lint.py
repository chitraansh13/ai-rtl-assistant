import argparse
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.hardware_tools.verilator import run_verilator_lint
from rtl_assistant.models.lint import LintStatus, LintReport


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for the linter CLI."""
    parser = argparse.ArgumentParser(description="Verilator Lint Runner CLI.")
    parser.add_argument(
        "--rtl",
        required=True,
        help="Path to the RTL module file."
    )
    parser.add_argument(
        "--report",
        help="Path to save the structured JSON lint report (optional)."
    )
    return parser.parse_args()


def write_json_report(report_path_str: str, report: LintReport) -> None:
    """Serialize and save the lint report to a JSON file."""
    report_path = Path(report_path_str)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = report.model_dump_json(indent=2)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(serialized)
    print(f"JSON lint report saved to: {report_path.resolve()}")


def main() -> int:
    args = parse_arguments()

    # Run the Verilator linter
    report = run_verilator_lint(args.rtl)

    # Print terminal summary
    print(f"\n==================================================")
    print(f"Verilator Lint Results for: {args.rtl}")
    print(f"==================================================")
    print(f"Status:      {report.status.value}")
    print(f"Lint Passed: {report.lint_passed}")
    print(f"Exit Code:   {report.exit_code}")
    print(f"Duration:    {report.duration_ms} ms")

    if report.error_type:
        print(f"\nError Details:")
        print(f"  Type:    {report.error_type}", file=sys.stderr)
        print(f"  Message: {report.error_message}", file=sys.stderr)

    if report.errors:
        print(f"\nParsed Errors ({len(report.errors)}):")
        for err in report.errors:
            print(f"  {err}")

    if report.warnings:
        print(f"\nParsed Warnings ({len(report.warnings)}):")
        for warn in report.warnings:
            print(f"  {warn}")

    print(f"\nFINAL RESULT: {report.status.value}")
    print(f"==================================================")

    # Write JSON report if requested
    if args.report:
        try:
            write_json_report(args.report, report)
        except Exception as e:
            print(f"INTERNAL ERROR: Failed to write JSON report: {e}", file=sys.stderr)
            return 1

    # Map status to exit code
    if report.status == LintStatus.PASS:
        return 0
    elif report.status == LintStatus.FAIL:
        return 1
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())
