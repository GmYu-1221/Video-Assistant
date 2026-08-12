from content_creator.config import get_env

from .openai_compatible import OpenAICompatibleProvider
from .provider import LLMProvider, MockLLMProvider


def get_provider(provider_name: str | None = None, model_name: str | None = None) -> LLMProvider:
    provider = (provider_name or get_env("LLM_PROVIDER", "openai-compatible")).lower()
    model = model_name or get_env("LLM_MODEL", "")
    if provider == "mock":
        return MockLLMProvider()
    api_key = get_env("OPENAI_API_KEY", "")
    if not api_key or not model:
        return MockLLMProvider()
    return OpenAICompatibleProvider(
        api_key=api_key,
        model_name=model,
        base_url=get_env("OPENAI_BASE_URL") or None,
    )
