import re
import subprocess
import time
from pathlib import Path

from rtl_assistant.hardware_tools.platform import adapt_path_for_host_tool, unix_tool_platform_mode, unix_tool_prefix
from rtl_assistant.models.synthesis import SynthesisReport, SynthesisStatus

TOP_MODULE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def quote_yosys_string(value: str) -> str:
    """Quote a string for safe use inside a Yosys -p command script."""

    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_yosys_command(rtl_path: Path, top_module: str) -> tuple[list[str], str, str]:
    """Build the cross-platform Yosys command and return the adapted RTL path and execution mode."""

    tool_path = adapt_path_for_host_tool(rtl_path)
    script = "; ".join(
        [
            f"read_verilog -sv {quote_yosys_string(tool_path)}",
            f"hierarchy -check -top {top_module}",
            "proc",
            "opt",
            "memory",
            "opt",
            "stat",
        ]
    )
    command = [*unix_tool_prefix("yosys"), "-Q", "-p", script]
    return command, tool_path, unix_tool_platform_mode()


def parse_yosys_diagnostics(stdout: str, stderr: str) -> tuple[list[str], list[str]]:
    """Extract warning and error lines conservatively from Yosys output."""

    warnings: list[str] = []
    errors: list[str] = []

    for raw_line in (stdout + "\n" + stderr).splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if not line:
            continue
        if "warning:" in lower or lower.startswith("warning"):
            warnings.append(line)
            continue
        if "error:" in lower or lower.startswith("error") or lower.startswith("errors:"):
            errors.append(line)

    return warnings, errors


def parse_yosys_stat_block(output: str) -> tuple[int | None, int | None, int | None, dict[str, int]]:
    """Parse a small, stable subset of Yosys stat output."""

    number_of_wires = None
    number_of_wire_bits = None
    number_of_cells = None
    cell_types: dict[str, int] = {}

    wires_match = re.findall(r"Number of wires:\s*(\d+)", output)
    wire_bits_match = re.findall(r"Number of wire bits:\s*(\d+)", output)
    cells_match = re.findall(r"Number of cells:\s*(\d+)", output)

    if wires_match:
        number_of_wires = int(wires_match[-1])
    if wire_bits_match:
        number_of_wire_bits = int(wire_bits_match[-1])
    if cells_match:
        number_of_cells = int(cells_match[-1])

    lines = output.splitlines()
    stat_start_index = None
    for index, line in enumerate(lines):
        if re.search(r"Number of cells:\s*\d+", line):
            stat_start_index = index + 1

    if stat_start_index is not None:
        for line in lines[stat_start_index:]:
            if not line.strip():
                break
            if line.lstrip().startswith("Number of "):
                continue
            if line.startswith("==="):
                break
            match = re.match(r"^\s*([^\s:]+)\s+(\d+)\s*$", line)
            if not match:
                if cell_types:
                    break
                continue
            cell_types[match.group(1)] = int(match.group(2))

    return number_of_wires, number_of_wire_bits, number_of_cells, cell_types


def detect_error_type(
    platform_mode: str,
    top_module: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    errors: list[str],
) -> tuple[str | None, str | None]:
    """Map common Yosys failure modes to stable typed error codes."""

    combined = "\n".join([stdout, stderr, *errors]).lower()

    if "module" in combined and "not found" in combined and top_module.lower() in combined:
        return "TOP_MODULE_NOT_FOUND", f"Top module '{top_module}' was not found during Yosys hierarchy checking."

    if "command not found" in combined or (exit_code == 127 and "yosys" in combined):
        if platform_mode == "windows_wsl":
            return "YOSYS_NOT_FOUND", "Yosys command not found inside WSL. Ensure it is installed in your WSL distribution."
        return "YOSYS_NOT_FOUND", "Yosys executable not found on the host machine. Ensure it is installed and added to your PATH."

    return None, None


def run_yosys_synthesis(
    rtl_path: str | Path,
    top_module: str,
    timeout_seconds: int = 30,
) -> SynthesisReport:
    """Run a deterministic Yosys synthesis flow and return a typed synthesis report."""

    start_time = time.perf_counter()
    rtl_path_obj = Path(rtl_path)

    if not rtl_path_obj.exists() or not rtl_path_obj.is_file():
        duration = int((time.perf_counter() - start_time) * 1000)
        return SynthesisReport(
            rtl_file=str(rtl_path_obj),
            top_module=top_module,
            tool="yosys",
            synthesis_passed=False,
            status=SynthesisStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type="RTL_FILE_NOT_FOUND",
            error_message=f"RTL file not found or is not a file: {rtl_path_obj}",
        )

    if not top_module or not TOP_MODULE_PATTERN.fullmatch(top_module):
        duration = int((time.perf_counter() - start_time) * 1000)
        return SynthesisReport(
            rtl_file=str(rtl_path_obj.resolve()),
            top_module=top_module,
            tool="yosys",
            synthesis_passed=False,
            status=SynthesisStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type="TOP_MODULE_NOT_FOUND",
            error_message=f"Invalid or missing top module name: {top_module!r}",
        )

    command, _, platform_mode = build_yosys_command(rtl_path_obj, top_module)

    try:
        result = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        duration = int((time.perf_counter() - start_time) * 1000)
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        warnings, errors = parse_yosys_diagnostics(stdout, stderr)
        error_type, error_message = detect_error_type(
            platform_mode=platform_mode,
            top_module=top_module,
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            errors=errors,
        )

        if error_type is None and result.returncode != 0 and any(
            "not found" in err.lower() and "module" in err.lower() for err in errors
        ):
            error_type = "TOP_MODULE_NOT_FOUND"
            error_message = f"Top module '{top_module}' was not found during Yosys hierarchy checking."

        if error_type is not None:
            status = SynthesisStatus.FAIL
            synthesis_passed = False
        elif result.returncode != 0 or errors:
            status = SynthesisStatus.FAIL
            synthesis_passed = False
        elif result.returncode == 0:
            status = SynthesisStatus.PASS
            synthesis_passed = True
        else:
            status = SynthesisStatus.UNKNOWN
            synthesis_passed = False

        number_of_wires, number_of_wire_bits, number_of_cells, cell_types = parse_yosys_stat_block(stdout)

        return SynthesisReport(
            rtl_file=str(rtl_path_obj.resolve()),
            top_module=top_module,
            tool="yosys",
            synthesis_passed=synthesis_passed,
            status=status,
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            warnings=warnings,
            errors=errors,
            timed_out=False,
            duration_ms=duration,
            error_type=error_type,
            error_message=error_message,
            number_of_wires=number_of_wires,
            number_of_wire_bits=number_of_wire_bits,
            number_of_cells=number_of_cells,
            cell_types=cell_types,
        )
    except FileNotFoundError:
        duration = int((time.perf_counter() - start_time) * 1000)
        if platform_mode == "windows_wsl":
            error_type = "WSL_NOT_FOUND"
            error_message = "WSL executable not found on the host machine. Ensure WSL is enabled and in your PATH."
        else:
            error_type = "YOSYS_NOT_FOUND"
            error_message = "Yosys executable not found on the host machine. Ensure it is installed and added to your PATH."
        return SynthesisReport(
            rtl_file=str(rtl_path_obj.resolve()),
            top_module=top_module,
            tool="yosys",
            synthesis_passed=False,
            status=SynthesisStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type=error_type,
            error_message=error_message,
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - start_time) * 1000)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        warnings, errors = parse_yosys_diagnostics(stdout, stderr)
        return SynthesisReport(
            rtl_file=str(rtl_path_obj.resolve()),
            top_module=top_module,
            tool="yosys",
            synthesis_passed=False,
            status=SynthesisStatus.FAIL,
            exit_code=None,
            stdout=stdout,
            stderr=stderr,
            warnings=warnings,
            errors=errors,
            timed_out=True,
            duration_ms=duration,
            error_type="SYNTHESIS_TIMEOUT",
            error_message=f"Synthesis command timed out after {timeout_seconds} seconds.",
        )
    except Exception as exc:
        duration = int((time.perf_counter() - start_time) * 1000)
        return SynthesisReport(
            rtl_file=str(rtl_path_obj.resolve()),
            top_module=top_module,
            tool="yosys",
            synthesis_passed=False,
            status=SynthesisStatus.FAIL,
            exit_code=None,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            timed_out=False,
            duration_ms=duration,
            error_type="SYNTHESIS_EXECUTION_ERROR",
            error_message=f"Subprocess startup or execution failed: {exc}",
        )
