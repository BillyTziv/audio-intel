import json
import logging
import re
from abc import ABC, abstractmethod

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str: ...


class OllamaProvider(LLMProvider):
    def __init__(self, url: str, model: str) -> None:
        self.url = url.rstrip("/")
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        try:
            resp = httpx.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": max_tokens},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=600.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("message") or {}).get("content", "") or ""
        except httpx.HTTPError as exc:
            raise LLMError(f"ollama request failed: {exc}") from exc


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMError("OPENAI_API_KEY is empty")
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0.1,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=600.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except httpx.HTTPError as exc:
            raise LLMError(f"openai request failed: {exc}") from exc


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is empty")
        self.api_key = api_key
        self.model = model

    def complete(self, system: str, user: str, *, max_tokens: int = 2048) -> str:
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": 0.1,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=600.0,
            )
            resp.raise_for_status()
            data = resp.json()
            parts = data.get("content") or []
            return "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        except httpx.HTTPError as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc


def get_provider() -> LLMProvider | None:
    s = get_settings()
    provider = (s.LLM_PROVIDER or "none").lower()
    if provider == "none":
        return None
    if provider == "ollama":
        return OllamaProvider(url=s.OLLAMA_URL, model=s.LLM_MODEL)
    if provider == "openai":
        return OpenAIProvider(api_key=s.OPENAI_API_KEY, model=s.LLM_MODEL)
    if provider == "anthropic":
        return AnthropicProvider(api_key=s.ANTHROPIC_API_KEY, model=s.LLM_MODEL)
    raise LLMError(f"unknown LLM_PROVIDER: {provider}")


def extract_json_block(text: str) -> dict | None:
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        cleaned = match.group(0).replace("```json", "").replace("```", "")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None
