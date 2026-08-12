from openai import OpenAI


class OpenAICompatibleProvider:
    """Provider for any service implementing OpenAI Chat Completions."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        if not model_name:
            raise ValueError("An LLM model name is required")
        self.model_name = model_name
        self.base_url = base_url
        self._client = client or OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return response.choices[0].message.content or ""
