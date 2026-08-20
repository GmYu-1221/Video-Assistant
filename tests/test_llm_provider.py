import json

from PIL import Image

import httpx
import pytest
from openai import OpenAI

from content_creator.services.llm.factory import get_provider
from content_creator.services.llm.openai_compatible import OpenAICompatibleProvider
from content_creator.services.llm.provider import MockLLMProvider
from content_creator.services.llm.router import require_agent_provider


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


def test_provider_uses_bounded_timeout_and_no_implicit_retries(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("content_creator.services.llm.openai_compatible.OpenAI", Client)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "17")
    OpenAICompatibleProvider(api_key="test-key", model_name="text-model", base_url="https://gateway.example/v1")
    assert captured["timeout"] == 17.0
    assert captured["max_retries"] == 0


def test_provider_falls_back_when_gateway_does_not_support_json_mode():
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if "response_format" in payload:
            return httpx.Response(400, json={"error": {"message": "unsupported response_format"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"operations": []}'}}]})

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="claude", client=client)

    assert provider.complete_json("return JSON") == '{"operations": []}'
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in requests[1]


def test_structured_output_falls_back_only_after_explicit_json_schema_rejection():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if payload.get("response_format", {}).get("type") == "json_schema":
            return httpx.Response(400, json={"error": {"message": "unsupported response_format json_schema"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"value":1}'}}]})

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="test", client=client)
    assert provider.complete_structured("return JSON", {"type": "object"}, "decision") == '{"value":1}'
    assert [item["response_format"]["type"] for item in requests] == ["json_schema", "json_object"]


def test_structured_output_sends_strict_json_schema():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"value":1}'}}]})

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="test", client=client)
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"], "additionalProperties": False}
    assert provider.complete_structured("return JSON", schema, "test decision") == '{"value":1}'
    assert captured["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "test_decision", "strict": True, "schema": schema},
    }


@pytest.mark.parametrize("status", [401, 404, 429, 500])
def test_structured_output_does_not_fallback_for_operational_errors(status):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(status, json={"error": {"message": "authentication, model, rate, or server failure"}})

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="test", client=client)
    with pytest.raises(Exception):
        provider.complete_structured("return JSON", {"type": "object"}, "decision")
    assert requests
    assert all(item["response_format"]["type"] == "json_schema" for item in requests)


def test_structured_output_does_not_fallback_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="test", client=client)
    with pytest.raises(Exception):
        provider.complete_structured("return JSON", {"type": "object"}, "decision")


def test_multimodal_provider_uses_gemini_asset_model_and_image_data(tmp_path):
    thumbnail = tmp_path / "thumbnail.jpg"
    Image.new("RGB", (32, 32), "#336699").save(thumbnail)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "gemini-3.6-flash"
        content = payload["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "select assets"}
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"image_tags": []}'}}]})

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="gemini-3.6-flash", client=client)
    assert provider.complete_multimodal("select assets", [str(thumbnail)]) == '{"image_tags": []}'


def test_multimodal_text_does_not_force_json_mode(tmp_path):
    thumbnail = tmp_path / "thumbnail.jpg"
    Image.new("RGB", (16, 16), "#123456").save(thumbnail)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "response_format" not in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": "<!doctype html><html></html>"}}]})

    client = OpenAI(api_key="test-key", base_url="https://gateway.example/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    provider = OpenAICompatibleProvider(api_key="test-key", model_name="animation", client=client)
    assert provider.complete_multimodal_text("build HTML", [str(thumbnail)]).startswith("<!doctype html>")


def test_agent_provider_rejects_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with pytest.raises(RuntimeError, match="non-mock"):
        require_agent_provider("animation")
