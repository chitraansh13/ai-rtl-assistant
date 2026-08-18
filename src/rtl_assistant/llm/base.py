from abc import ABC, abstractmethod

from rtl_assistant.models.llm import LLMResponse


class LLMProvider(ABC):
    """Provider-neutral interface for local or remote language models."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Current configured model identifier."""

    @abstractmethod
    def generate(self, prompt: str) -> LLMResponse:
        """Generate a text response for the given prompt."""
