import json

import httpx
from openai import OpenAI

from content_creator.services.llm.factory import get_provider
from content_creator.services.llm.openai_compatible import OpenAICompatibleProvider
from content_creator.services.llm.provider import MockLLMProvider


def test_provider_uses_openai_compatible_chat_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://gateway.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "claude-sonnet-4-20250514"
        assert payload["messages"] == [{"role": "user", "content": "plan video"}]
        assert payload["temperature"] == 0
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"scenes": []}'},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    client = OpenAI(
        api_key="test-key",
        base_url="https://gateway.example/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model_name="claude-sonnet-4-20250514",
        base_url="https://gateway.example/v1",
        client=client,
    )

    assert provider.complete("plan video") == '{"scenes": []}'


def test_provider_initialization_and_missing_configuration(monkeypatch):
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model_name="kimi-k2.5",
        base_url="https://gateway.example/v1",
    )
    assert provider.model_name == "kimi-k2.5"
    assert provider.base_url == "https://gateway.example/v1"

    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-20250514")
    assert get_provider().model_name == "mock"
    assert MockLLMProvider('{"x":1}').complete("test") == '{"x":1}'
