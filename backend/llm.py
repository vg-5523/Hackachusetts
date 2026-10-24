"""LLM_Wrapper: the single LLM call site for the backend.

This module exposes exactly one function, ``call_llm``, which sends a prompt to
the Google Gemini ``generateContent`` API over HTTPS and returns the model's
text. The ``LLM_API_KEY`` environment variable is read at call time and is never
logged, printed, or written to disk. When it is unset or empty, ``call_llm``
raises before any network request is made.

If ``LLM_API_KEY`` is not already set in the environment, a ``.env`` file at the
repository root is loaded (via ``python-dotenv``) so local runs can configure
the key without exporting it. The model can be overridden with ``LLM_MODEL``.

Thinking is kept minimal for speed: the request first asks for
``thinkingBudget: 0``. If a model rejects that with an HTTP 400, the call falls
back to a low thinking budget, then to no thinking config at all. The accepted
mode is recorded in the module global ``LAST_THINKING_MODE`` so a caller can
report what worked. On HTTP 429 the call waits 5 seconds and retries up to 3
times; on a 5xx it retries once after 5 seconds.
"""

import os
import time

import httpx
from dotenv import load_dotenv

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-3.5-flash"
_TIMEOUT_S = 20.0
_RETRY_WAIT_S = 5.0
_MAX_429_RETRIES = 3

# Thinking configs tried in order: minimal (0), then low, then none. The
# accepted one is written here for reporting. This never holds the key.
_THINKING_MODES = (
    ("thinkingBudget=0", {"thinkingConfig": {"thinkingBudget": 0}}),
    ("thinkingBudget=low", {"thinkingConfig": {"thinkingBudget": 128}}),
    ("no-thinkingConfig", {}),
)
LAST_THINKING_MODE = _THINKING_MODES[0][0]


def call_llm(prompt: str) -> str:
    """Send ``prompt`` to the Gemini API and return the generated text.

    Reads ``LLM_API_KEY`` at call time; if unset or empty, raises a
    ``RuntimeError`` whose message contains ``LLM_API_KEY`` before any network
    request. The key is sent only in the ``x-goog-api-key`` header and never
    appears in logs, exceptions, or return values. A 20 second timeout is used;
    on HTTP 429 the call waits 5 seconds and retries up to 3 times; on a 5xx it
    retries once after 5 seconds; any other failure raises an error without the
    key. Thinking is minimized with a graceful fallback (see module docstring).
    """
    global LAST_THINKING_MODE

    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        load_dotenv()  # repo-root .env fallback, only when not already set
        api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set")

    model = os.environ.get("LLM_MODEL") or _DEFAULT_MODEL
    url = f"{_API_BASE}/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    last_400: int | None = None
    for mode_label, thinking in _THINKING_MODES:
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                **thinking,
            },
        }

        # Send with retries: 429 up to 3x, 5xx once, transport error once.
        attempt_429 = 0
        tried_5xx = False
        tried_transport = False
        while True:
            try:
                response = httpx.post(
                    url, headers=headers, json=body, timeout=_TIMEOUT_S
                )
            except httpx.HTTPError as exc:
                if not tried_transport:
                    tried_transport = True
                    time.sleep(_RETRY_WAIT_S)
                    continue
                raise RuntimeError(
                    f"LLM request failed: {type(exc).__name__}"
                ) from None

            if response.status_code == 429 and attempt_429 < _MAX_429_RETRIES:
                attempt_429 += 1
                time.sleep(_RETRY_WAIT_S)
                continue
            if response.status_code >= 500 and not tried_5xx:
                tried_5xx = True
                time.sleep(_RETRY_WAIT_S)
                continue
            break

        if response.status_code == 400:
            # Likely a rejected thinking config; try the next, lighter mode.
            last_400 = 400
            continue
        if response.status_code != 200:
            raise RuntimeError(
                f"LLM request failed with status {response.status_code}"
            )

        LAST_THINKING_MODE = mode_label
        try:
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"LLM response could not be parsed: {type(exc).__name__}"
            ) from None

    raise RuntimeError(f"LLM request failed with status {last_400 or 400}")
