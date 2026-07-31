import argparse
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import List, Tuple

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.models.simulation import FinalStatus, SimulationReport


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generic SystemVerilog simulation runner."
    )
    parser.add_argument(
        "--rtl",
        required=True,
        help="Path to the RTL module file."
    )
    parser.add_argument(
        "--testbench",
        required=True,
        help="Path to the testbench file."
    )
    parser.add_argument(
        "--output",
        help="Path to the output compiled simulation file (optional)."
    )
    parser.add_argument(
        "--report",
        help="Path to save the structured JSON report (optional)."
    )
    return parser.parse_args()


def resolve_input_path(path_str: str, repository_root: Path) -> Path:
    """Resolve input path string to a Path object, supporting absolute and relative paths."""
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    return (repository_root / path).resolve()


def run_command(command: List[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a command using subprocess.run with specified parameters."""
    return subprocess.run(
        command,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def is_failure_line(line: str) -> bool:
    """Check if a line indicates a genuine failure."""
    # Ignore successful zero-failure summary lines
    if re.search(r"\b(?:failed\s+tests|failures|failed)\s*:\s*0\b", line, re.IGNORECASE):
        return False
    # Treat lines containing an explicit failure marker as failure
    if re.search(r"\b(?:fail|failed|fails|failing)\b", line, re.IGNORECASE):
        return True
    return False


def is_success_line(line: str) -> bool:
    """Check if a line indicates a genuine success."""
    if re.search(r"\b(?:pass|passed|passes|passing)\b", line, re.IGNORECASE):
        return True
    return False


def classify_simulation_output(stdout: str, stderr: str, exit_code: int) -> Tuple[FinalStatus, bool, int]:
    """Classify the simulation output and return (final_status, simulation_passed, process_exit_code)."""
    has_failure = False
    has_success = False

    for line in stdout.splitlines() + stderr.splitlines():
        if is_failure_line(line):
            has_failure = True
        elif is_success_line(line):
            has_success = True

    if has_failure:
        print("FINAL RESULT: FAIL")
        return FinalStatus.FAIL, False, 1
    elif exit_code != 0:
        print(f"Simulation failed with exit code {exit_code}.", file=sys.stderr)
        return FinalStatus.FAIL, False, 1
    elif has_success:
        print("FINAL RESULT: PASS")
        return FinalStatus.PASS, True, 0
    else:
        print("FINAL RESULT: UNKNOWN")
        print("The testbench did not print a recognizable pass or fail marker (e.g., 'PASS', 'PASSED', 'FAIL', or 'FAILED').")
        return FinalStatus.UNKNOWN, False, 2


def main() -> int:
    total_start = time.perf_counter()
    repository_root = Path(__file__).resolve().parent.parent

    args = parse_arguments()

    # Initialize the structured report dictionary
    report = {
        "rtl_file": "",
        "testbench_file": "",
        "simulation_output_file": "",
        "compile_passed": False,
        "simulation_passed": False,
        "final_status": FinalStatus.FAIL,
        "compile_exit_code": None,
        "simulation_exit_code": None,
        "compile_stdout": "",
        "compile_stderr": "",
        "simulation_stdout": "",
        "simulation_stderr": "",
        "compile_timed_out": False,
        "simulation_timed_out": False,
        "compile_duration_ms": None,
        "simulation_duration_ms": None,
        "total_duration_ms": 0,
    }

    exit_code = 1

    try:
        rtl_path = resolve_input_path(args.rtl, repository_root)
        testbench_path = resolve_input_path(args.testbench, repository_root)

        report["rtl_file"] = str(rtl_path)
        report["testbench_file"] = str(testbench_path)

        if args.output:
            output_path = resolve_input_path(args.output, repository_root)
        else:
            output_path = testbench_path.parent / "simulation_output.vvp"
        report["simulation_output_file"] = str(output_path)

        # 1. Verify files exist
        if not rtl_path.exists() or not rtl_path.is_file():
            err_msg = f"RTL file not found or is not a file: {rtl_path}"
            print(f"ERROR: {err_msg}", file=sys.stderr)
            report["error_type"] = "RTL_FILE_NOT_FOUND"
            report["error_message"] = err_msg
            report["final_status"] = FinalStatus.FAIL
            exit_code = 1
            return exit_code

        if not testbench_path.exists() or not testbench_path.is_file():
            err_msg = f"Testbench file not found or is not a file: {testbench_path}"
            print(f"ERROR: {err_msg}", file=sys.stderr)
            report["error_type"] = "TESTBENCH_FILE_NOT_FOUND"
            report["error_message"] = err_msg
            report["final_status"] = FinalStatus.FAIL
            exit_code = 1
            return exit_code

        # 2. Compile Design
        compile_start = time.perf_counter()
        compile_command = [
            "iverilog",
            "-g2012",
            "-o",
            str(output_path),
            str(rtl_path),
            str(testbench_path),
        ]
        print("Compiling design...")
        try:
            result = run_command(compile_command, timeout=30.0)
            compile_end = time.perf_counter()
            report["compile_duration_ms"] = int((compile_end - compile_start) * 1000)

            report["compile_exit_code"] = result.returncode
            report["compile_stdout"] = result.stdout or ""
            report["compile_stderr"] = result.stderr or ""

            if result.returncode != 0:
                print("COMPILATION FAILED", file=sys.stderr)
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                report["final_status"] = FinalStatus.FAIL
                exit_code = 1
                return exit_code

            report["compile_passed"] = True
            print("Compilation successful")

        except FileNotFoundError:
            compile_end = time.perf_counter()
            report["compile_duration_ms"] = int((compile_end - compile_start) * 1000)
            err_msg = "Error: 'iverilog' executable not found. Make sure Icarus Verilog is installed and added to your PATH."
            print("COMPILATION FAILED", file=sys.stderr)
            print(err_msg, file=sys.stderr)
            report["error_type"] = "IVERILOG_NOT_FOUND"
            report["error_message"] = err_msg
            report["final_status"] = FinalStatus.FAIL
            exit_code = 1
            return exit_code

        except subprocess.TimeoutExpired as e:
            compile_end = time.perf_counter()
            report["compile_duration_ms"] = int((compile_end - compile_start) * 1000)
            err_msg = "Error: Compilation timed out after 30.0 seconds."
            print("COMPILATION FAILED", file=sys.stderr)
            print(err_msg, file=sys.stderr)
            report["compile_timed_out"] = True
            report["error_type"] = "COMPILATION_TIMEOUT"
            report["error_message"] = err_msg
            report["final_status"] = FinalStatus.FAIL
            report["compile_stdout"] = e.stdout or ""
            report["compile_stderr"] = e.stderr or ""
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr)
            exit_code = 1
            return exit_code

        # 3. Execute Simulation
        sim_start = time.perf_counter()
        sim_command = ["vvp", str(output_path)]
        print("Running simulation...")
        try:
            sim_result = run_command(sim_command, timeout=30.0)
            sim_end = time.perf_counter()
            report["simulation_duration_ms"] = int((sim_end - sim_start) * 1000)

            report["simulation_exit_code"] = sim_result.returncode
            report["simulation_stdout"] = sim_result.stdout or ""
            report["simulation_stderr"] = sim_result.stderr or ""

            stdout = sim_result.stdout or ""
            stderr = sim_result.stderr or ""

            # Print captured stdout and stderr
            if stdout:
                print(stdout, end="")
            if stderr:
                print(stderr, end="", file=sys.stderr)

            # Classify simulation output
            final_status, simulation_passed, status_exit_code = classify_simulation_output(
                stdout, stderr, sim_result.returncode
            )
            report["final_status"] = final_status
            report["simulation_passed"] = simulation_passed
            exit_code = status_exit_code
            return exit_code

        except FileNotFoundError:
            sim_end = time.perf_counter()
            report["simulation_duration_ms"] = int((sim_end - sim_start) * 1000)
            err_msg = "Error: 'vvp' executable not found. Make sure Icarus Verilog is installed and added to your PATH."
            print(f"ERROR: {err_msg}", file=sys.stderr)
            report["error_type"] = "VVP_NOT_FOUND"
            report["error_message"] = err_msg
            report["final_status"] = FinalStatus.FAIL
            exit_code = 1
            return exit_code

        except subprocess.TimeoutExpired as e:
            sim_end = time.perf_counter()
            report["simulation_duration_ms"] = int((sim_end - sim_start) * 1000)
            err_msg = "Error: Simulation timed out after 30 seconds."
            print(f"ERROR: {err_msg}", file=sys.stderr)
            report["simulation_timed_out"] = True
            report["error_type"] = "SIMULATION_TIMEOUT"
            report["error_message"] = err_msg
            report["final_status"] = FinalStatus.FAIL
            report["simulation_stdout"] = e.stdout or ""
            report["simulation_stderr"] = e.stderr or ""
            if e.stdout:
                print(e.stdout, end="")
            if e.stderr:
                print(e.stderr, end="", file=sys.stderr)
            exit_code = 1
            return exit_code

    finally:
        total_end = time.perf_counter()
        report["total_duration_ms"] = int((total_end - total_start) * 1000)

        # Write JSON report if requested
        if args.report:
            try:
                # Validate the report data using Pydantic SimulationReport
                report_model = SimulationReport(**report)
                serialized_json = report_model.model_dump_json(indent=2)

                # Write the file
                report_path = Path(args.report)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                with open(report_path, "w", encoding="utf-8") as f:
                    f.write(serialized_json)
                print(f"JSON report saved to: {report_path.resolve()}")
            except Exception as e:
                # Catch Pydantic validation or file write errors
                print("INTERNAL ERROR: Report validation or generation failed!", file=sys.stderr)
                print(f"Error details:\n{e}", file=sys.stderr)
                # Ensure we return a non-zero exit code on failure
                sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())