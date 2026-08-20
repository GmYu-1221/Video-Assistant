from typing import Protocol

class LLMProvider(Protocol):
    model_name: str
    def complete(self, prompt: str) -> str: ...
    def complete_json(self, prompt: str) -> str: ...
    def complete_structured(self, prompt: str, schema: dict, schema_name: str) -> str: ...
    def complete_multimodal(self, prompt: str, image_paths: list[str]) -> str: ...
    def complete_multimodal_structured(self, prompt: str, image_paths: list[str], schema: dict, schema_name: str) -> str: ...
    def complete_multimodal_text(self, prompt: str, image_paths: list[str]) -> str: ...

class MockLLMProvider:
    model_name = "mock"
    def __init__(self, response: str = "") -> None:
        self.response = response
    def complete(self, prompt: str) -> str:
        return self.response
    def complete_json(self, prompt: str) -> str:
        return self.response
    def complete_structured(self, prompt: str, schema: dict, schema_name: str) -> str:
        return self.response
    def complete_multimodal(self, prompt: str, image_paths: list[str]) -> str:
        return self.response
    def complete_multimodal_structured(self, prompt: str, image_paths: list[str], schema: dict, schema_name: str) -> str:
        return self.response
    def complete_multimodal_text(self, prompt: str, image_paths: list[str]) -> str:
        return self.response
