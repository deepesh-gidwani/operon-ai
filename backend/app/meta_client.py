"""Real client for the Meta Model API (OpenAI-compatible chat completions).

All LLM inference in Operon AI goes through this module, using the model
configured in backend env (default ``muse-spark-1.3``). The API key is read
from ``MODEL_API_KEY`` server-side and never leaves the backend.

Transient failures (timeouts, connection errors, HTTP 429/5xx) are retried a
bounded number of times. Anything else fails honestly with MetaAPIError —
this module never returns fake content.
"""

from __future__ import annotations

import json
import logging
import time

import httpx

from . import config

log = logging.getLogger("operon.meta")


class MetaAPIError(RuntimeError):
    """Raised for any Meta Model API failure. Never returns fake content."""


_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _extract_json(text: str) -> str:
    """Strip code fences so prompt-constrained JSON can be parsed."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned


class MetaClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.MODEL_API_KEY
        self.base_url = (base_url or config.MODEL_API_URL).rstrip("/")
        self.model = model or config.MODEL_NAME
        self.timeout_s = timeout_s if timeout_s is not None else config.LLM_TIMEOUT_S
        self.max_retries = max_retries if max_retries is not None else config.LLM_MAX_RETRIES

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _post_once(self, url: str, payload: dict) -> httpx.Response:
        try:
            return httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise MetaAPIError(
                f"Meta Model API request timed out after {self.timeout_s:g}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise MetaAPIError(f"Meta Model API request failed: {exc}") from exc

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 2000) -> str:
        """POST one chat completion and return the assistant text verbatim."""
        if not self.api_key:
            raise MetaAPIError(
                "MODEL_API_KEY is not configured; cannot call the Meta Model API."
            )
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        last_error: MetaAPIError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._post_once(url, payload)
            except MetaAPIError as exc:
                # Timeouts and connection errors are retryable; auth errors are not.
                last_error = exc
                if attempt < self.max_retries:
                    log.warning("Meta API attempt %d failed, retrying: %s", attempt + 1, exc)
                    time.sleep(config.LLM_RETRY_BACKOFF_S * (attempt + 1))
                    continue
                raise
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    return str(data["choices"][0]["message"]["content"])
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise MetaAPIError(
                        f"Unexpected Meta Model API response: {resp.text[:500]}"
                    ) from exc
            if resp.status_code in _RETRYABLE_STATUS and attempt < self.max_retries:
                log.warning(
                    "Meta API HTTP %d, retrying (attempt %d)", resp.status_code, attempt + 1
                )
                time.sleep(config.LLM_RETRY_BACKOFF_S * (attempt + 1))
                continue
            body = resp.text[:500]
            raise MetaAPIError(f"Meta Model API HTTP {resp.status_code}: {body}")
        raise last_error or MetaAPIError("Meta Model API request failed.")

    def chat_json(self, messages: list[dict[str, str]], max_tokens: int = 2000) -> dict:
        """Chat completion constrained to a single JSON object.

        Malformed JSON is retried (bounded): the model gets one clarifying
        follow-up per attempt asking for the bare JSON object again.
        """
        last_text = ""
        for attempt in range(self.max_retries + 1):
            attempt_messages = messages
            if attempt > 0:
                attempt_messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply was not valid JSON. Reply again with "
                            "exactly one JSON object and nothing else — no code fences, "
                            "no prose."
                        ),
                    },
                ]
            text = self.chat(attempt_messages, max_tokens=max_tokens)
            last_text = text
            try:
                parsed = json.loads(_extract_json(text))
            except ValueError:
                log.warning("Model returned malformed JSON (attempt %d)", attempt + 1)
                continue
            if not isinstance(parsed, dict):
                log.warning("Model returned a JSON non-object (attempt %d)", attempt + 1)
                continue
            return parsed
        raise MetaAPIError(f"Model did not return valid JSON: {last_text[:500]}")
