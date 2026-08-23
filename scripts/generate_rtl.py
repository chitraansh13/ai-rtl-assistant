import argparse
import json
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from pydantic import ValidationError

from rtl_assistant.llm.config import get_default_ollama_base_url, get_default_ollama_model
from rtl_assistant.llm.ollama import OllamaProvider
from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.rtl_generation import RTLGenerationResult, RTLGenerationStatus
from rtl_assistant.rtl.generator import AIRTLGenerator


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for RTL generation."""

    parser = argparse.ArgumentParser(description="Generate SystemVerilog RTL from a validated HardwareSpec JSON file.")
    parser.add_argument("spec_path", help="Path to the validated HardwareSpec JSON file.")
    parser.add_argument("--model", default=get_default_ollama_model(), help="Ollama model name.")
    parser.add_argument("--base-url", default=get_default_ollama_base_url(), help="Ollama base URL.")
    parser.add_argument("--output", help="Optional path to save generated RTL.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw model output on failure.")
    return parser.parse_args()


def load_hardware_spec(spec_path_str: str) -> HardwareSpec:
    """Read and validate a HardwareSpec JSON file."""

    spec_path = Path(spec_path_str)
    if not spec_path.exists() or not spec_path.is_file():
        raise FileNotFoundError(f"HardwareSpec file not found or is not a file: {spec_path}")

    raw_json = spec_path.read_text(encoding="utf-8")
    json.loads(raw_json)
    return HardwareSpec.model_validate_json(raw_json)


def print_success(result: RTLGenerationResult) -> None:
    """Print a concise successful generation summary."""

    rtl_text = result.rtl or ""
    print("========================================")
    print("AI RTL Generator")
    print("========================================")
    print(f"Provider:       {result.provider}")
    print(f"Model:          {result.model}")
    print(f"Attempts:       {result.attempts}")
    print(f"Status:         {result.status.value}")
    print("")
    print(f"Module:         {result.module_name}")
    print(f"RTL chars:      {len(rtl_text)}")
    print("========================================")


def print_failure(result: RTLGenerationResult, show_raw: bool) -> None:
    """Print a concise failed generation summary."""

    print("========================================", file=sys.stderr)
    print("AI RTL Generator", file=sys.stderr)
    print("========================================", file=sys.stderr)
    print(f"Provider:       {result.provider}", file=sys.stderr)
    print(f"Model:          {result.model}", file=sys.stderr)
    print(f"Attempts:       {result.attempts}", file=sys.stderr)
    print(f"Status:         {result.status.value}", file=sys.stderr)
    print(f"Error Type:     {result.error_type}", file=sys.stderr)
    print(f"Reason:         {result.error_message}", file=sys.stderr)
    if show_raw and result.raw_model_output:
        print("\nRaw Model Output:", file=sys.stderr)
        print(result.raw_model_output, file=sys.stderr)
    print("========================================", file=sys.stderr)


def write_output(output_path_str: str, result: RTLGenerationResult) -> None:
    """Write generated RTL text to a file."""

    rtl_text = result.rtl
    assert rtl_text is not None

    output_path = Path(output_path_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(normalize_rtl_output_text(rtl_text), encoding="utf-8")
    print("")
    print("Generated RTL saved to:")
    print(output_path.resolve())


def normalize_rtl_output_text(rtl_text: str) -> str:
    """Normalize generated RTL for stable tool-compatible file output."""

    return rtl_text.rstrip() + "\n"


def default_rtl_output_path(hardware_spec: HardwareSpec) -> Path:
    """Return the default generated RTL output path for one validated module."""

    return Path("generated") / f"{hardware_spec.module_name}.sv"


def warn_if_output_filename_mismatches_module(output_path: Path, module_name: str) -> None:
    """Warn when the explicit output filename stem does not match the validated module name."""

    if output_path.stem == module_name:
        return

    print(
        f"WARNING: Output filename '{output_path.name}' does not match module name '{module_name}'. "
        f"Verilator may report DECLFILENAME. Recommended filename: '{module_name}.sv'.",
        file=sys.stderr,
    )


def main() -> int:
    args = parse_arguments()

    try:
        hardware_spec = load_hardware_spec(args.spec_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in HardwareSpec file: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print("ERROR: HardwareSpec validation failed.", file=sys.stderr)
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error["loc"]) or "root"
            print(f"{location}: {error['msg']}", file=sys.stderr)
        return 1

    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    generator = AIRTLGenerator(provider)
    result = generator.generate(hardware_spec)

    if result.status == RTLGenerationStatus.SUCCESS:
        print_success(result)
        output_path = Path(args.output) if args.output else default_rtl_output_path(hardware_spec)
        if args.output:
            warn_if_output_filename_mismatches_module(output_path, hardware_spec.module_name)
        write_output(str(output_path), result)
        return 0

    print_failure(result, show_raw=args.show_raw)
    return 1


if __name__ == "__main__":
    sys.exit(main())
