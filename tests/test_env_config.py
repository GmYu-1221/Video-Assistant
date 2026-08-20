from content_creator.config import ENV_FILE, get_env, load_project_env
from content_creator.services.llm.factory import get_provider
from content_creator.services.llm.router import get_agent_provider


def test_project_env_file_is_loaded_from_repository_root():
    assert ENV_FILE.name == ".env"
    assert ENV_FILE.parent.name == "Video-Assistant"
    assert load_project_env() is True
    assert get_env("LLM_PROVIDER") is not None


def test_openai_compatible_configuration_initializes_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.vectorengine.cn/v1")
    monkeypatch.setenv("LLM_MODEL", "fallback-model")
    monkeypatch.setenv("DIRECTOR_MODEL", "claude-sonnet-4-20250514")

    provider = get_agent_provider("director")

    assert provider.model_name == "claude-sonnet-4-20250514"
    assert provider.base_url == "https://api.vectorengine.cn/v1"


def test_missing_api_key_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-20250514")

    assert get_provider().model_name == "mock"


def test_agent_model_overrides_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "fallback-model")
    monkeypatch.setenv("DIRECTOR_MODEL", "director-model")
    monkeypatch.setenv("ANIMATION_MODEL", "animation-model")
    monkeypatch.setenv("COPY_FITTING_MODEL", "copy-model")

    assert get_agent_provider("director").model_name == "director-model"
    assert get_agent_provider("animation").model_name == "animation-model"
    assert get_agent_provider("copy_fitting").model_name == "copy-model"
