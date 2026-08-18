import re
import subprocess
import time
from pathlib import Path

from rtl_assistant.models.simulation import FinalStatus, SimulationReport


def resolve_input_path(path_str: str | Path, base_dir: str | Path | None = None) -> Path:
    """Resolve an input path using an optional base directory."""

    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    if base_dir is not None:
        return (Path(base_dir) / path).resolve()
    return path.resolve()


def run_command(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with consistent defaults."""

    return subprocess.run(
        command,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def is_failure_line(line: str) -> bool:
    """Check whether a line indicates a genuine functional failure."""

    if re.search(r"\b(?:failed\s+tests|failures|failed)\s*:\s*0\b", line, re.IGNORECASE):
        return False
    return re.search(r"\b(?:fail|failed|fails|failing)\b", line, re.IGNORECASE) is not None


def is_success_line(line: str) -> bool:
    """Check whether a line indicates a genuine functional success."""

    return re.search(r"\b(?:pass|passed|passes|passing)\b", line, re.IGNORECASE) is not None


def classify_simulation_output(stdout: str, stderr: str, exit_code: int) -> tuple[FinalStatus, bool]:
    """Classify simulation output into a typed final status."""

    has_failure = False
    has_success = False

    for line in stdout.splitlines() + stderr.splitlines():
        if is_failure_line(line):
            has_failure = True
        elif is_success_line(line):
            has_success = True

    if has_failure:
        return FinalStatus.FAIL, False
    if exit_code != 0:
        return FinalStatus.FAIL, False
    if has_success:
        return FinalStatus.PASS, True
    return FinalStatus.UNKNOWN, False


def run_simulation(
    rtl_path: str | Path,
    testbench_path: str | Path,
    output_path: str | Path | None = None,
    compile_timeout_seconds: float = 30.0,
    simulation_timeout_seconds: float = 30.0,
    base_dir: str | Path | None = None,
) -> SimulationReport:
    """Compile and simulate RTL with Icarus Verilog and return a typed report."""

    total_start = time.perf_counter()
    rtl_path_obj = resolve_input_path(rtl_path, base_dir=base_dir)
    testbench_path_obj = resolve_input_path(testbench_path, base_dir=base_dir)

    if output_path is not None:
        output_path_obj = resolve_input_path(output_path, base_dir=base_dir)
    else:
        output_path_obj = testbench_path_obj.parent / "simulation_output.vvp"

    report = {
        "rtl_file": str(rtl_path_obj),
        "testbench_file": str(testbench_path_obj),
        "simulation_output_file": str(output_path_obj),
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
        "error_type": None,
        "error_message": None,
    }
    stop_after_current_stage = False

    try:
        if not rtl_path_obj.exists() or not rtl_path_obj.is_file():
            report["error_type"] = "RTL_FILE_NOT_FOUND"
            report["error_message"] = f"RTL file not found or is not a file: {rtl_path_obj}"
            stop_after_current_stage = True

        if not stop_after_current_stage and (not testbench_path_obj.exists() or not testbench_path_obj.is_file()):
            report["error_type"] = "TESTBENCH_FILE_NOT_FOUND"
            report["error_message"] = f"Testbench file not found or is not a file: {testbench_path_obj}"
            stop_after_current_stage = True

        if not stop_after_current_stage:
            compile_start = time.perf_counter()
            compile_command = [
                "iverilog",
                "-g2012",
                "-o",
                str(output_path_obj),
                str(rtl_path_obj),
                str(testbench_path_obj),
            ]
            try:
                compile_result = run_command(compile_command, timeout=compile_timeout_seconds)
                report["compile_duration_ms"] = int((time.perf_counter() - compile_start) * 1000)
                report["compile_exit_code"] = compile_result.returncode
                report["compile_stdout"] = compile_result.stdout or ""
                report["compile_stderr"] = compile_result.stderr or ""
                if compile_result.returncode != 0:
                    stop_after_current_stage = True
                else:
                    report["compile_passed"] = True
            except FileNotFoundError:
                report["compile_duration_ms"] = int((time.perf_counter() - compile_start) * 1000)
                report["error_type"] = "IVERILOG_NOT_FOUND"
                report["error_message"] = (
                    "Error: 'iverilog' executable not found. Make sure Icarus Verilog is installed and added to your PATH."
                )
                stop_after_current_stage = True
            except subprocess.TimeoutExpired as exc:
                report["compile_duration_ms"] = int((time.perf_counter() - compile_start) * 1000)
                report["compile_timed_out"] = True
                report["compile_stdout"] = exc.stdout or ""
                report["compile_stderr"] = exc.stderr or ""
                report["error_type"] = "COMPILATION_TIMEOUT"
                report["error_message"] = f"Error: Compilation timed out after {compile_timeout_seconds} seconds."
                stop_after_current_stage = True

        if not stop_after_current_stage:
            simulation_start = time.perf_counter()
            simulation_command = ["vvp", str(output_path_obj)]
            try:
                simulation_result = run_command(simulation_command, timeout=simulation_timeout_seconds)
                report["simulation_duration_ms"] = int((time.perf_counter() - simulation_start) * 1000)
                report["simulation_exit_code"] = simulation_result.returncode
                report["simulation_stdout"] = simulation_result.stdout or ""
                report["simulation_stderr"] = simulation_result.stderr or ""

                final_status, simulation_passed = classify_simulation_output(
                    report["simulation_stdout"],
                    report["simulation_stderr"],
                    simulation_result.returncode,
                )
                report["final_status"] = final_status
                report["simulation_passed"] = simulation_passed
            except FileNotFoundError:
                report["simulation_duration_ms"] = int((time.perf_counter() - simulation_start) * 1000)
                report["error_type"] = "VVP_NOT_FOUND"
                report["error_message"] = (
                    "Error: 'vvp' executable not found. Make sure Icarus Verilog is installed and added to your PATH."
                )
            except subprocess.TimeoutExpired as exc:
                report["simulation_duration_ms"] = int((time.perf_counter() - simulation_start) * 1000)
                report["simulation_timed_out"] = True
                report["simulation_stdout"] = exc.stdout or ""
                report["simulation_stderr"] = exc.stderr or ""
                report["error_type"] = "SIMULATION_TIMEOUT"
                report["error_message"] = f"Error: Simulation timed out after {simulation_timeout_seconds} seconds."
    finally:
        report["total_duration_ms"] = int((time.perf_counter() - total_start) * 1000)

    return SimulationReport(**report)
