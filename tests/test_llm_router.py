from content_creator.services.llm.router import get_agent_provider


def test_agent_model_routing_uses_per_agent_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_MODEL", "fallback-model")
    monkeypatch.setenv("DIRECTOR_MODEL", "director-model")
    monkeypatch.setenv("REMOTION_MODEL", "remotion-model")
    monkeypatch.setenv("CHAT_MODEL", "chat-model")

    assert get_agent_provider("director").model_name == "director-model"
    assert get_agent_provider("remotion").model_name == "remotion-model"
    assert get_agent_provider("chat").model_name == "chat-model"
