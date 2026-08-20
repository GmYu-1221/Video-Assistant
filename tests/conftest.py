import pytest


@pytest.fixture(autouse=True)
def deterministic_default_provider(monkeypatch):
    """Unit tests opt into real provider routing explicitly when needed."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
