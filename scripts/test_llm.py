import argparse
import sys
from pathlib import Path

# Add 'src' to sys.path to enable imports without installing
repository_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repository_root / "src"))

from rtl_assistant.llm.ollama import OllamaProvider


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments for direct provider testing."""

    parser = argparse.ArgumentParser(description="Send a simple prompt directly to OllamaProvider.")
    parser.add_argument("prompt", help="Prompt text to send to the provider.")
    parser.add_argument("--model", default="qwen2.5-coder:7b", help="Ollama model name.")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    provider = OllamaProvider(model=args.model, base_url=args.base_url)
    response = provider.generate(args.prompt)

    print("========================================")
    print("LLM Provider Test")
    print("========================================")
    print(f"Success:       {response.success}")
    print(f"Provider:      {response.provider}")
    print(f"Model:         {response.model}")
    print(f"Duration:      {response.duration_ms} ms")

    if response.success:
        print("Status:        SUCCESS")
        print("")
        print(response.response_text)
        print("========================================")
        return 0

    print("Status:        FAIL")
    print(f"Error Type:    {response.error_type}")
    print(f"Reason:        {response.error_message}")
    if response.response_text.strip():
        print("")
        print(response.response_text)
    print("========================================")
    return 1


if __name__ == "__main__":
    sys.exit(main())
