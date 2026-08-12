"""Small, safe smoke test for the configured OpenAI-compatible LLM provider."""

from __future__ import annotations

import argparse

from content_creator.config import get_env
from content_creator.services.llm.router import get_agent_provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the configured LLM provider")
    parser.add_argument(
        "--agent",
        choices=("director", "remotion", "chat"),
        default="director",
        help="Agent model route to test (default: director)",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly: LLM connection OK",
        help="Prompt sent to the provider",
    )
    args = parser.parse_args()

    provider = get_agent_provider(args.agent)
    base_url = get_env("OPENAI_BASE_URL") or "(OpenAI default endpoint)"
    print(f"provider={get_env('LLM_PROVIDER', 'openai-compatible')}")
    print(f"agent={args.agent}")
    print(f"model={provider.model_name}")
    print(f"base_url={base_url}")

    if provider.model_name == "mock":
        print("status=MOCK (LLM_PROVIDER=mock, OPENAI_API_KEY, or model configuration requires attention)")
        return 0

    print("status=READY")
    try:
        response = provider.complete(args.prompt)
    except Exception as exc:  # CLI smoke test should report provider errors cleanly.
        print(f"status=ERROR ({type(exc).__name__}: {exc})")
        return 1

    print("status=OK")
    print("response:")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
