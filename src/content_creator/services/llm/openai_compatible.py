import base64
import os
import re
from pathlib import Path

from openai import OpenAI


class OpenAICompatibleProvider:
    """Provider for any service implementing OpenAI Chat Completions."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        client: OpenAI | None = None,
        timeout_seconds: float | None = None,
        max_retries: int = 0,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        if not model_name:
            raise ValueError("An LLM model name is required")
        self.model_name = model_name
        self.base_url = base_url
        if client is not None:
            self._client = client
        else:
            configured_timeout = timeout_seconds
            if configured_timeout is None:
                try:
                    configured_timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))
                except ValueError:
                    configured_timeout = 90.0
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=max(1.0, configured_timeout),
                max_retries=max(0, max_retries),
            )

    def complete(self, prompt: str) -> str:
        return self._complete(prompt)

    def complete_json(self, prompt: str) -> str:
        """Prefer JSON mode, while retaining compatibility with Claude-style gateways."""
        try:
            return self._complete(prompt, response_format={"type": "json_object"})
        except Exception as exc:
            if not _response_format_unsupported(exc):
                raise
            return self._complete(prompt)

    def complete_structured(self, prompt: str, schema: dict, schema_name: str) -> str:
        response_format = {"type": "json_schema", "json_schema": {"name": _schema_name(schema_name), "strict": True, "schema": schema}}
        try:
            return self._complete(prompt, response_format=response_format)
        except Exception as exc:
            if not _response_format_unsupported(exc):
                raise
            return self.complete_json(prompt)

    def complete_multimodal(self, prompt: str, image_paths: list[str]) -> str:
        try:
            return self._complete_multimodal(prompt, image_paths, response_format={"type": "json_object"})
        except Exception as exc:
            if not _response_format_unsupported(exc):
                raise
            return self._complete_multimodal(prompt, image_paths)

    def complete_multimodal_structured(self, prompt: str, image_paths: list[str], schema: dict, schema_name: str) -> str:
        response_format = {"type": "json_schema", "json_schema": {"name": _schema_name(schema_name), "strict": True, "schema": schema}}
        try:
            return self._complete_multimodal(prompt, image_paths, response_format=response_format)
        except Exception as exc:
            if not _response_format_unsupported(exc):
                raise
            return self.complete_multimodal(prompt, image_paths)

    def complete_multimodal_text(self, prompt: str, image_paths: list[str]) -> str:
        return self._complete_multimodal(prompt, image_paths)

    def _complete_multimodal(self, prompt: str, image_paths: list[str], *, response_format: dict | None = None) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for path in image_paths[:6]:
            data = Path(path).read_bytes()
            if len(data) > 2_000_000:
                continue
            encoded = base64.b64encode(data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}})
        kwargs = {"response_format": response_format} if response_format else {}
        response = self._client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": content}], temperature=0, **kwargs)
        return response.choices[0].message.content or ""

    def _complete(self, prompt: str, **kwargs: object) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            **kwargs,
        )
        return response.choices[0].message.content or ""


def _response_format_unsupported(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status not in {400, 422}:
        return False
    message = str(exc).lower()
    parameter = "response_format" in message or "json_schema" in message or "json schema" in message
    unsupported = any(marker in message for marker in ("unsupported", "not support", "unknown parameter", "unrecognized", "not allowed"))
    return parameter and unsupported


def _schema_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    return (normalized or "agent_output")[:64]
