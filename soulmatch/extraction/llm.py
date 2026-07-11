"""Provider-agnostic LLM client for profile extraction.

Providers:
  gemini    - Google AI Studio (free tier available); REST, no extra SDK
  anthropic - Claude via the official anthropic SDK
  local     - any OpenAI-compatible chat-completions server on the local
              network (LM Studio, Ollama, etc.) — no API key needed
  mock      - regex-based offline fallback so the app works without any key

Switch with LLM_PROVIDER in .env.
"""

from __future__ import annotations

import json
import re

import requests

from .. import config


class LLMError(RuntimeError):
    pass


def complete_json(prompt: str, provider: str | None = None) -> dict:
    """Send a prompt expected to yield a single JSON object; return it parsed."""
    provider = (provider or config.LLM_PROVIDER).lower()
    if provider == "gemini":
        raw = _gemini(prompt)
    elif provider == "anthropic":
        raw = _anthropic(prompt)
    elif provider == "local":
        raw = _local(prompt)
    elif provider == "mock":
        raise LLMError("mock provider has no completion endpoint")
    else:
        raise LLMError(f"Unknown LLM_PROVIDER: {provider}")
    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start == -1:
        raise LLMError(f"No JSON object in model output: {raw[:200]!r}")
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(text, start)
    except json.JSONDecodeError as e:
        raise LLMError(f"Could not parse JSON from model output: {raw[:200]!r}") from e
    return obj


def _gemini(prompt: str) -> str:
    if not config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent"
    )
    resp = requests.post(
        url,
        params={"key": config.GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected Gemini response shape: {data}") from e


def _local(prompt: str) -> str:
    try:
        resp = requests.post(
            config.LOCAL_LLM_URL,
            json={
                "model": config.LOCAL_LLM_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You respond with only a single JSON object and nothing else.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 2048,
            },
            timeout=120,
        )
    except requests.ConnectionError as e:
        raise LLMError(
            f"Could not reach local LLM server at {config.LOCAL_LLM_URL} — is it running?"
        ) from e
    if resp.status_code != 200:
        raise LLMError(f"Local LLM server error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected local LLM response shape: {data}") from e


def _anthropic(prompt: str) -> str:
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY is not set (see .env.example)")
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError as e:
        raise LLMError("Anthropic rate limit hit — retry shortly") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Network error reaching the Anthropic API") from e
    if response.stop_reason == "refusal":
        raise LLMError("Model declined this content")
    return next((b.text for b in response.content if b.type == "text"), "")
