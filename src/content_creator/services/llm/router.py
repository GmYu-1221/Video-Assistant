from content_creator.config import get_env

from .factory import get_provider
from .provider import LLMProvider


_AGENT_MODEL_ENV = {
    "director": "DIRECTOR_MODEL",
    "remotion": "REMOTION_MODEL",
    "chat": "CHAT_MODEL",
}


def get_agent_provider(agent_name: str) -> LLMProvider:
    model_env = _AGENT_MODEL_ENV.get(agent_name.lower(), f"{agent_name.upper()}_MODEL")
    model = get_env(model_env) or get_env("LLM_MODEL")
    return get_provider(get_env("LLM_PROVIDER", "openai-compatible"), model)
