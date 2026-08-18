import subprocess
import time
from pathlib import Path

from rtl_assistant.hardware_tools.platform import adapt_path_for_host_tool, unix_tool_platform_mode, unix_tool_prefix
from rtl_assistant.models.lint import LintStatus, LintReport


def build_verilator_command(rtl_path: Path) -> tuple[list[str], str, str]:
    """Build the Verilator command list, path string, and execution mode based on the current OS."""
    tool_path = adapt_path_for_host_tool(rtl_path)
    command = [*unix_tool_prefix("verilator"), "--lint-only", "-Wall", tool_path]
    return command, tool_path, unix_tool_platform_mode()


def run_verilator_lint(rtl_path: str | Path, timeout_seconds: int = 30) -> LintReport:
    """Run Verilator linter on the specified RTL file via the platform-appropriate method."""
    start_time = time.perf_counter()
    rtl_path_obj = Path(rtl_path)
    
    # 1. Check if RTL file exists
    if not rtl_path_obj.exists() or not rtl_path_obj.is_file():
        duration = int((time.perf_counter() - start_time) * 1000)
        return LintReport(
            rtl_file=str(rtl_path_obj),
            tool="verilator",
            lint_passed=False,
            status=LintStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type="RTL_FILE_NOT_FOUND",
            error_message=f"RTL file not found or is not a file: {rtl_path_obj}"
        )
        
    command, lint_file_path, platform_mode = build_verilator_command(rtl_path_obj)
    
    try:
        result = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False
        )
        duration = int((time.perf_counter() - start_time) * 1000)
        
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        exit_code = result.returncode
        
        # Check if Verilator command not found (inside WSL or natively)
        if exit_code == 127 or "command not found" in stderr.lower() or "not found" in stderr.lower():
            err_msg = (
                "Verilator command not found inside WSL. Ensure it is installed in your WSL distribution."
                if platform_mode == "windows_wsl" else
                "Verilator command not found on the host machine. Ensure it is installed and added to your PATH."
            )
            return LintReport(
                rtl_file=str(rtl_path_obj),
                tool="verilator",
                lint_passed=False,
                status=LintStatus.FAIL,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                warnings=[],
                errors=[],
                timed_out=False,
                duration_ms=duration,
                error_type="VERILATOR_NOT_FOUND",
                error_message=err_msg
            )
            
        # Parse warnings and errors
        warnings = []
        errors = []
        for line in (stdout + stderr).splitlines():
            line = line.strip()
            if line.startswith("%Warning"):
                warnings.append(line)
            elif line.startswith("%Error"):
                errors.append(line)
                
        # Determine status and lint_passed
        if exit_code != 0 or len(errors) > 0:
            status = LintStatus.FAIL
            lint_passed = False
        elif exit_code == 0 and len(errors) == 0 and len(warnings) == 0:
            status = LintStatus.PASS
            lint_passed = True
        else:
            status = LintStatus.UNKNOWN
            lint_passed = False
            
        return LintReport(
            rtl_file=str(rtl_path_obj),
            tool="verilator",
            lint_passed=lint_passed,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            warnings=warnings,
            errors=errors,
            timed_out=False,
            duration_ms=duration
        )
        
    except FileNotFoundError:
        duration = int((time.perf_counter() - start_time) * 1000)
        if platform_mode == "windows_wsl":
            err_type = "WSL_NOT_FOUND"
            err_msg = "WSL executable not found on the host machine. Ensure WSL is enabled and in your PATH."
        else:
            err_type = "VERILATOR_NOT_FOUND"
            err_msg = "Verilator executable not found on the host machine. Ensure it is installed and added to your PATH."
            
        return LintReport(
            rtl_file=str(rtl_path_obj),
            tool="verilator",
            lint_passed=False,
            status=LintStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type=err_type,
            error_message=err_msg
        )
    except subprocess.TimeoutExpired as e:
        duration = int((time.perf_counter() - start_time) * 1000)
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        return LintReport(
            rtl_file=str(rtl_path_obj),
            tool="verilator",
            lint_passed=False,
            status=LintStatus.FAIL,
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            warnings=[],
            errors=[],
            timed_out=True,
            duration_ms=duration,
            error_type="LINT_TIMEOUT",
            error_message=f"Lint command timed out after {timeout_seconds} seconds."
        )
    except Exception as e:
        duration = int((time.perf_counter() - start_time) * 1000)
        return LintReport(
            rtl_file=str(rtl_path_obj),
            tool="verilator",
            lint_passed=False,
            status=LintStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type="LINT_EXECUTION_ERROR",
            error_message=f"Subprocess startup or execution failed: {e}"
        )
