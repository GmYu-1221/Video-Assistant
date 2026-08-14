from typing import Protocol

class LLMProvider(Protocol):
    model_name: str
    def complete(self, prompt: str) -> str: ...
    def complete_json(self, prompt: str) -> str: ...
    def complete_multimodal(self, prompt: str, image_paths: list[str]) -> str: ...

class MockLLMProvider:
    model_name = "mock"
    def __init__(self, response: str = "") -> None:
        self.response = response
    def complete(self, prompt: str) -> str:
        return self.response
    def complete_json(self, prompt: str) -> str:
        return self.response
    def complete_multimodal(self, prompt: str, image_paths: list[str]) -> str:
        return self.response
