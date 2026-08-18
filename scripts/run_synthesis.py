import argparse
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.hardware_tools.yosys import run_yosys_synthesis
from rtl_assistant.models.synthesis import SynthesisReport, SynthesisStatus


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for the synthesis CLI."""

    parser = argparse.ArgumentParser(description="Yosys synthesis runner CLI.")
    parser.add_argument("--rtl", required=True, help="Path to the RTL module file.")
    parser.add_argument("--top", required=True, help="Name of the top module.")
    parser.add_argument("--report", help="Path to save the structured JSON synthesis report (optional).")
    return parser.parse_args()


def write_json_report(report_path_str: str, report: SynthesisReport) -> None:
    """Serialize and save the synthesis report to a JSON file."""

    report_path = Path(report_path_str)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"JSON synthesis report saved to: {report_path.resolve()}")


def print_summary(report: SynthesisReport) -> None:
    """Print a concise synthesis summary."""

    print("\n========================================")
    print("Yosys Synthesis")
    print("========================================")
    print(f"RTL:         {report.rtl_file}")
    print(f"Top Module:  {report.top_module}")
    print(f"Status:      {report.status.value}")
    print(f"Passed:      {report.synthesis_passed}")
    print(f"Exit Code:   {report.exit_code}")
    print(f"Duration:    {report.duration_ms} ms")

    if report.number_of_wires is not None:
        print(f"Wires:       {report.number_of_wires}")
    if report.number_of_wire_bits is not None:
        print(f"Wire Bits:   {report.number_of_wire_bits}")
    if report.number_of_cells is not None:
        print(f"Cells:       {report.number_of_cells}")
    if report.cell_types:
        print("Cell Types:")
        for cell_type, count in sorted(report.cell_types.items()):
            print(f"  {cell_type}: {count}")

    if report.error_type:
        print("\nError Details:")
        print(f"  Type:    {report.error_type}")
        print(f"  Message: {report.error_message}")

    if report.errors:
        print(f"\nParsed Errors ({len(report.errors)}):")
        for error in report.errors:
            print(f"  {error}")

    if report.warnings:
        print(f"\nParsed Warnings ({len(report.warnings)}):")
        for warning in report.warnings:
            print(f"  {warning}")

    print(f"\nFINAL RESULT: {report.status.value}")
    print("========================================")


def status_to_exit_code(status: SynthesisStatus) -> int:
    """Map synthesis status to process exit code."""

    if status == SynthesisStatus.PASS:
        return 0
    if status == SynthesisStatus.FAIL:
        return 1
    return 2


def main() -> int:
    args = parse_arguments()
    report = run_yosys_synthesis(args.rtl, args.top)
    print_summary(report)

    if args.report:
        try:
            write_json_report(args.report, report)
        except Exception as exc:
            print(f"INTERNAL ERROR: Failed to write JSON report: {exc}", file=sys.stderr)
            return 1

    return status_to_exit_code(report.status)


if __name__ == "__main__":
    sys.exit(main())
