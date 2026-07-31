import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import List, Tuple


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


def compile_design(rtl_path: Path, testbench_path: Path, output_path: Path) -> int:
    """Compile the RTL and testbench files using iverilog."""
    command = [
        "iverilog",
        "-g2012",
        "-o",
        str(output_path),
        str(rtl_path),
        str(testbench_path),
    ]
    print("Compiling design...")
    try:
        result = run_command(command, timeout=30.0)
    except FileNotFoundError:
        print("COMPILATION FAILED", file=sys.stderr)
        print("Error: 'iverilog' executable not found. Make sure Icarus Verilog is installed and added to your PATH.", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as e:
        print("COMPILATION FAILED", file=sys.stderr)
        print("Error: Compilation timed out after 30.0 seconds.", file=sys.stderr)
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return 1

    if result.returncode != 0:
        print("COMPILATION FAILED", file=sys.stderr)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return 1

    print("Compilation successful")
    return 0


def execute_simulation(output_path: Path) -> Tuple[int, str, str]:
    """Execute the compiled simulation using vvp."""
    command = ["vvp", str(output_path)]
    print("Running simulation...")
    try:
        result = run_command(command, timeout=30.0)
        return result.returncode, result.stdout or "", result.stderr or ""
    except FileNotFoundError:
        return -1, "", ""
    except subprocess.TimeoutExpired as e:
        return -2, e.stdout or "", e.stderr or ""


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


def classify_simulation_output(stdout: str, stderr: str, exit_code: int) -> int:
    """Classify the simulation output to determine pass/fail status by examining line-by-line."""
    has_failure = False
    has_success = False

    for line in stdout.splitlines() + stderr.splitlines():
        if is_failure_line(line):
            has_failure = True
        elif is_success_line(line):
            has_success = True

    if has_failure:
        print("FINAL RESULT: FAIL")
        return 1
    elif exit_code != 0:
        print(f"Simulation failed with exit code {exit_code}.", file=sys.stderr)
        return 1
    elif has_success:
        print("FINAL RESULT: PASS")
        return 0
    else:
        print("FINAL RESULT: UNKNOWN")
        print("The testbench did not print a recognizable pass or fail marker (e.g., 'PASS', 'PASSED', 'FAIL', or 'FAILED').")
        return 2


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent

    args = parse_arguments()

    rtl_path = resolve_input_path(args.rtl, repository_root)
    testbench_path = resolve_input_path(args.testbench, repository_root)

    if not rtl_path.exists() or not rtl_path.is_file():
        print(f"ERROR: RTL file not found or is not a file: {rtl_path}", file=sys.stderr)
        return 1

    if not testbench_path.exists() or not testbench_path.is_file():
        print(f"ERROR: Testbench file not found or is not a file: {testbench_path}", file=sys.stderr)
        return 1

    if args.output:
        output_path = resolve_input_path(args.output, repository_root)
    else:
        output_path = testbench_path.parent / "simulation_output.vvp"

    # Compile design
    compile_exit = compile_design(rtl_path, testbench_path, output_path)
    if compile_exit != 0:
        return compile_exit

    # Execute simulation
    return_code, stdout, stderr = execute_simulation(output_path)

    if return_code == -1:
        print("ERROR: 'vvp' executable not found. Make sure Icarus Verilog is installed and added to your PATH.", file=sys.stderr)
        return 1
    elif return_code == -2:
        print("ERROR: Simulation timed out after 30 seconds.", file=sys.stderr)
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        return 1

    # Print captured stdout and stderr
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="", file=sys.stderr)

    # Classify the simulation output
    return classify_simulation_output(stdout, stderr, return_code)


if __name__ == "__main__":
    sys.exit(main())