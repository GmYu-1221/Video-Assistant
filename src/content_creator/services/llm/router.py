from content_creator.config import get_env

from .factory import get_provider
from .provider import LLMProvider


_AGENT_MODEL_ENV = {
    "director": "DIRECTOR_MODEL",
    "editorial": "EDITORIAL_MODEL",
    "copy_fitting": "COPY_FITTING_MODEL",
    "animation": "ANIMATION_MODEL",
    "asset": "ASSET_MODEL",
    "article": "ARTICLE_MODEL",
}


def get_agent_provider(agent_name: str) -> LLMProvider:
    model_env = _AGENT_MODEL_ENV.get(agent_name.lower(), f"{agent_name.upper()}_MODEL")
    model = get_env(model_env)
    if agent_name.lower() in {"article", "asset"}:
        model = model or get_env("ASSET_MODEL") or get_env("LLM_MODEL")
    else:
        model = model or get_env("LLM_MODEL")
    return get_provider(get_env("LLM_PROVIDER", "openai-compatible"), model)


def require_agent_provider(agent_name: str) -> LLMProvider:
    provider = get_agent_provider(agent_name)
    if provider.model_name == "mock":
        raise RuntimeError(f"{agent_name} Agent requires a configured non-mock LLM provider")
    return provider
