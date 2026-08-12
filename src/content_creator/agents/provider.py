from typing import Protocol

class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...

class MockLLMProvider:
    def complete(self, prompt: str) -> str:
        return ""
