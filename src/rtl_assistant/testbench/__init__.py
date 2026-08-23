"""Testbench package exports kept lazy to avoid circular imports."""

__all__ = [
    "DeterministicTestbenchGenerator",
    "AITestbenchGenerator",
    "TESTBENCH_PROMPT_VERSION",
]


def __getattr__(name: str):
    if name == "DeterministicTestbenchGenerator":
        from rtl_assistant.testbench.deterministic import DeterministicTestbenchGenerator

        return DeterministicTestbenchGenerator
    if name == "AITestbenchGenerator":
        from rtl_assistant.testbench.generator import AITestbenchGenerator

        return AITestbenchGenerator
    if name == "TESTBENCH_PROMPT_VERSION":
        from rtl_assistant.testbench.prompts import TESTBENCH_PROMPT_VERSION

        return TESTBENCH_PROMPT_VERSION
    raise AttributeError(name)
