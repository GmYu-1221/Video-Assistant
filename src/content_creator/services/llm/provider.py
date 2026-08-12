from typing import Protocol

class LLMProvider(Protocol):
    model_name: str
    def complete(self, prompt: str) -> str: ...

class MockLLMProvider:
    model_name = "mock"
    def __init__(self, response: str = "") -> None:
        self.response = response
    def complete(self, prompt: str) -> str:
        return self.response
