import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.llm.config import get_default_ollama_base_url, get_default_ollama_model


MIN_PYTHON = (3, 10)
REPO_REQUIRED_DIRECTORIES = ("src", "scripts", "examples")


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    detail: str


def main() -> int:
    results: list[CheckResult] = []
    ollama_url = get_default_ollama_base_url()
    ollama_model = get_default_ollama_model()

    results.append(check_python_version())
    results.extend(check_python_imports())
    results.extend(check_repo_structure())
    results.extend(check_hardware_tools())
    results.extend(check_ollama(ollama_url, ollama_model))

    print_report(results, ollama_url, ollama_model)
    return 0


def check_python_version() -> CheckResult:
    """Verify the supported Python interpreter version."""

    version = sys.version_info
    version_text = platform.python_version()
    if version >= MIN_PYTHON:
        return CheckResult("Python", "PASS", f"{version_text} (supported, requires {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)")
    return CheckResult("Python", "FAIL", f"{version_text} detected; requires {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+")


def check_python_imports() -> list[CheckResult]:
    """Verify importable Python dependencies used by the project."""

    checks: list[CheckResult] = []
    dependency_map = {
        "Pydantic": "pydantic",
        "Project package": "rtl_assistant",
    }
    for label, module_name in dependency_map.items():
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", None)
            detail = f"imported successfully{f' ({version})' if version else ''}"
            checks.append(CheckResult(label, "PASS", detail))
        except Exception as exc:
            checks.append(CheckResult(label, "FAIL", f"import failed: {exc}"))
    return checks


def check_repo_structure() -> list[CheckResult]:
    """Confirm that key repository directories exist."""

    checks: list[CheckResult] = []
    for directory_name in REPO_REQUIRED_DIRECTORIES:
        path = repository_root / directory_name
        if path.exists() and path.is_dir():
            checks.append(CheckResult(f"Repo dir: {directory_name}", "PASS", str(path)))
        else:
            checks.append(CheckResult(f"Repo dir: {directory_name}", "FAIL", f"missing required directory: {path}"))
    return checks


def check_hardware_tools() -> list[CheckResult]:
    """Check the current platform's hardware tool availability."""

    checks: list[CheckResult] = []
    checks.append(check_native_tool("Icarus Verilog", "iverilog", ["iverilog", "-V"]))
    checks.append(check_native_tool("vvp", "vvp", ["vvp", "-V"]))

    if platform.system() == "Windows":
        wsl_result = check_wsl_availability()
        checks.append(wsl_result)
        if wsl_result.status != "PASS":
            checks.append(CheckResult("Verilator", "MISSING", "cannot check 'verilator' because WSL is unavailable"))
            checks.append(CheckResult("Yosys", "MISSING", "cannot check 'yosys' because WSL is unavailable"))
            return checks

        checks.append(check_wsl_tool("Verilator", "verilator", ["wsl", "verilator", "--version"]))
        checks.append(check_wsl_tool("Yosys", "yosys", ["wsl", "yosys", "-V"]))
    else:
        checks.append(check_native_tool("Verilator", "verilator", ["verilator", "--version"]))
        checks.append(check_native_tool("Yosys", "yosys", ["yosys", "-V"]))

    return checks


def check_native_tool(label: str, executable: str, version_command: list[str]) -> CheckResult:
    """Check a native executable via PATH lookup and optional version query."""

    resolved = shutil.which(executable)
    if resolved is None:
        return CheckResult(label, "MISSING", f"'{executable}' not found in PATH")

    version = run_version_command(version_command)
    detail = f"{resolved}"
    if version:
        detail = f"{detail} | {version}"
    return CheckResult(label, "PASS", detail)


def check_wsl_availability() -> CheckResult:
    """Check whether WSL is available on the Windows host."""

    wsl_executable = shutil.which("wsl")
    if wsl_executable is None:
        return CheckResult("WSL", "MISSING", "Windows adapters for Verilator/Yosys require 'wsl' on PATH")
    return CheckResult("WSL", "PASS", wsl_executable)


def check_wsl_tool(label: str, tool_name: str, version_command: list[str]) -> CheckResult:
    """Check one WSL-hosted hardware tool from Windows."""

    version = run_version_command(version_command)
    if version is None:
        return CheckResult(
            label,
            "MISSING",
            f"'{tool_name}' did not respond through WSL; ensure it is installed inside WSL",
        )
    return CheckResult(label, "PASS", version)


def run_version_command(command: list[str]) -> str | None:
    """Run a small version command and return a concise first line when available."""

    try:
        completed = subprocess.run(
            command,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None

    if completed.returncode != 0:
        return None

    output = (completed.stdout or completed.stderr or "").strip()
    if not output:
        return None
    return output.splitlines()[0]


def check_ollama(base_url: str, model_name: str) -> list[CheckResult]:
    """Check Ollama executable presence, server reachability, and model availability."""

    checks: list[CheckResult] = []
    executable = shutil.which("ollama")
    if executable is None:
        checks.append(CheckResult("Ollama executable", "MISSING", "not found in PATH"))
    else:
        checks.append(CheckResult("Ollama executable", "PASS", executable))

    tags_url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with request.urlopen(tags_url, timeout=5) as response:
            raw_text = response.read().decode("utf-8")
        payload = json.loads(raw_text)
    except error.URLError as exc:
        message = f"server not reachable at {base_url}: {exc.reason}"
        if executable is not None:
            checks.append(CheckResult("Ollama server", "WARN", message))
            checks.append(CheckResult(f"Ollama model: {model_name}", "WARN", "server not reachable, model availability unknown"))
        else:
            checks.append(CheckResult("Ollama server", "WARN", message))
            checks.append(CheckResult(f"Ollama model: {model_name}", "WARN", "Ollama not installed or server not running"))
        return checks
    except json.JSONDecodeError as exc:
        checks.append(CheckResult("Ollama server", "WARN", f"reachable at {base_url} but returned invalid JSON: {exc}"))
        checks.append(CheckResult(f"Ollama model: {model_name}", "WARN", "model availability unknown due to invalid Ollama response"))
        return checks
    except Exception as exc:
        checks.append(CheckResult("Ollama server", "WARN", f"unexpected check error: {exc}"))
        checks.append(CheckResult(f"Ollama model: {model_name}", "WARN", "model availability unknown"))
        return checks

    checks.append(CheckResult("Ollama server", "PASS", f"reachable at {base_url}"))
    model_names = extract_ollama_models(payload)
    if model_name in model_names:
        checks.append(CheckResult(f"Ollama model: {model_name}", "PASS", "model available locally"))
    else:
        checks.append(
            CheckResult(
                f"Ollama model: {model_name}",
                "MISSING",
                "server is running but model is not available locally; run 'ollama pull'",
            )
        )
    return checks


def extract_ollama_models(payload: object) -> set[str]:
    """Extract model names from the Ollama /api/tags response."""

    if not isinstance(payload, dict):
        return set()
    models = payload.get("models")
    if not isinstance(models, list):
        return set()

    names: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def print_report(results: list[CheckResult], ollama_url: str, ollama_model: str) -> None:
    """Print the environment report in a human-readable form."""

    print("AI RTL Assistant Environment Check")
    print("")
    print(f"Platform: {platform.system() or 'Unknown'}")
    print(f"Python executable: {sys.executable}")
    print(f"Ollama URL default: {ollama_url}")
    print(f"Ollama model default: {ollama_model}")
    print("")

    for result in results:
        print(f"{result.name}: {result.status}")
        print(f"  {result.detail}")

    deterministic_ready = all(
        status_is_pass(results, name)
        for name in ("Python", "Pydantic", "Project package", "Repo dir: src", "Repo dir: scripts", "Repo dir: examples", "Icarus Verilog", "vvp")
    ) and all(
        status_is_pass(results, name)
        for name in required_platform_tools()
    )

    ai_ready = deterministic_ready and status_is_pass(results, "Ollama server") and status_is_pass(
        results,
        f"Ollama model: {ollama_model}",
    )

    print("")
    print("Overall:")
    if deterministic_ready:
        print("  Deterministic pipeline: READY")
    else:
        print("  Deterministic pipeline: NOT READY")

    if ai_ready:
        print("  AI features: READY")
    else:
        print("  AI features: NOT READY")
        print("  Note: deterministic Step 14 testbench rendering does not require Ollama.")


def required_platform_tools() -> tuple[str, ...]:
    """Return the platform-specific hardware tools required for the deterministic flow."""

    if platform.system() == "Windows":
        return ("WSL", "Verilator", "Yosys")
    return ("Verilator", "Yosys")


def status_is_pass(results: list[CheckResult], name: str) -> bool:
    """Return True when one named check is present and passing."""

    for result in results:
        if result.name == name:
            return result.status == "PASS"
    return False


if __name__ == "__main__":
    raise SystemExit(main())
