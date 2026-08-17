import base64
import os
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
        except Exception:
            return self._complete(prompt)

    def complete_multimodal(self, prompt: str, image_paths: list[str]) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for path in image_paths[:6]:
            data = Path(path).read_bytes()
            if len(data) > 2_000_000:
                continue
            encoded = base64.b64encode(data).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}})
        response = self._client.chat.completions.create(model=self.model_name, messages=[{"role": "user", "content": content}], temperature=0, response_format={"type": "json_object"})
        return response.choices[0].message.content or ""

    def _complete(self, prompt: str, **kwargs: object) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            **kwargs,
        )
        return response.choices[0].message.content or ""
