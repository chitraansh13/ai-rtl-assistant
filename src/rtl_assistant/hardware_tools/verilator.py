import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Optional
from rtl_assistant.models.lint import LintStatus, LintReport


def to_wsl_path(path: str | Path) -> str:
    """Convert a Windows absolute path to a WSL path, leaving Unix-style paths intact."""
    path_str = str(path).replace('\\', '/')
    
    # Check if path starts with a Windows drive letter, e.g. E:/... or e:/...
    if len(path_str) >= 2 and path_str[1] == ':' and path_str[0].isalpha():
        drive = path_str[0].lower()
        rest = path_str[2:]
        if not rest.startswith('/'):
            rest = '/' + rest
        return f"/mnt/{drive}{rest}"
        
    return path_str


def run_verilator_lint(rtl_path: str | Path, timeout_seconds: int = 30) -> LintReport:
    """Run Verilator linter on the specified RTL file via WSL."""
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
        
    wsl_rtl_path = to_wsl_path(rtl_path_obj)
    
    # 2. Run Verilator command via WSL
    command = ["wsl", "verilator", "--lint-only", "-Wall", wsl_rtl_path]
    
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
        
        # Check if Verilator command not found inside WSL or WSL failed
        # Typically WSL returns exit code 127 if command inside it is not found
        if exit_code == 127 or "command not found" in stderr.lower() or "not found" in stderr.lower():
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
                error_message="Verilator command not found inside WSL. Ensure it is installed in your WSL distribution."
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
        # FAIL if nonzero exit code, any parsed Errors, or timeout/tool missing
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
            error_type="WSL_NOT_FOUND",
            error_message="WSL executable not found on the host machine. Ensure WSL is enabled and in your PATH."
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
