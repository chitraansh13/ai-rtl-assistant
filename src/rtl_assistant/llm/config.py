import os


DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"


def get_default_ollama_base_url() -> str:
    """Return the configured Ollama base URL with a sensible local default."""

    return os.getenv("RTL_ASSISTANT_OLLAMA_URL", DEFAULT_OLLAMA_BASE_URL).strip() or DEFAULT_OLLAMA_BASE_URL


def get_default_ollama_model() -> str:
    """Return the configured Ollama model name with a sensible local default."""

    return os.getenv("RTL_ASSISTANT_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
