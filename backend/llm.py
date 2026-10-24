"""LLM_Wrapper: the single LLM call site for the backend.

This module exposes exactly one function, ``call_llm``, which reads the
``LLM_API_KEY`` environment variable at call time. The module imports cleanly
with ``LLM_API_KEY`` unset: the key is never read at import time, and no network
call is made unless ``call_llm`` is invoked with a key present.

The provider endpoint and model are configurable via the optional
``LLM_API_URL`` and ``LLM_MODEL`` environment variables so the wrapper can point
at any OpenAI-compatible chat-completions API without code changes.
"""

import os

import httpx

DEFAULT_LLM_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_LLM_MODEL = "gpt-4o-mini"


def call_llm(prompt: str) -> str:
    """Send ``prompt`` to the configured LLM provider and return the reply text.

    The ``LLM_API_KEY`` environment variable is read at call time. If it is
    unset or empty, a ``RuntimeError`` whose message contains ``LLM_API_KEY`` is
    raised before any network request is made.

    The request targets an OpenAI-compatible chat-completions endpoint. The
    endpoint and model default to sensible values and can be overridden with the
    ``LLM_API_URL`` and ``LLM_MODEL`` environment variables.
    """
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set")

    api_url = os.environ.get("LLM_API_URL") or DEFAULT_LLM_API_URL
    model = os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = httpx.post(api_url, headers=headers, json=payload, timeout=60.0)
    response.raise_for_status()
    data = response.json()

    # Defensive parsing of an OpenAI-compatible response shape.
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text

    return ""
