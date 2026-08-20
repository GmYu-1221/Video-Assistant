from content_creator.services.llm.router import get_agent_provider


def test_agent_model_routing_uses_per_agent_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_MODEL", "fallback-model")
    monkeypatch.setenv("DIRECTOR_MODEL", "director-model")
    monkeypatch.setenv("ANIMATION_MODEL", "animation-model")
    monkeypatch.setenv("EDITORIAL_MODEL", "editorial-model")
    monkeypatch.setenv("ASSET_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("ARTICLE_MODEL", "article-model")

    assert get_agent_provider("director").model_name == "director-model"
    assert get_agent_provider("animation").model_name == "animation-model"
    assert get_agent_provider("editorial").model_name == "editorial-model"
    assert get_agent_provider("asset").model_name == "gemini-3.6-flash"
    assert get_agent_provider("article").model_name == "article-model"
