"""Thin provider clients over httpx (no extra SDKs). Returns text + token usage (None if unknown)."""
from dataclasses import dataclass
from typing import Optional
import httpx
from .config import key_for


class LLMError(Exception):
    pass


class BudgetError(LLMError):
    """Spend/call cap reached."""


@dataclass
class LLMResult:
    text: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


def _merge(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Providers need alternating roles; merge consecutive same-role messages."""
    out: list[tuple[str, str]] = []
    for role, text in messages:
        if out and out[-1][0] == role:
            out[-1] = (role, out[-1][1] + "\n\n" + text)
        else:
            out.append((role, text))
    return out


class AnthropicClient:
    def __init__(self, model: str, key: str, timeout: float = 25):
        self.model, self.key, self.timeout = model, key, timeout

    def generate(self, system, messages, max_tokens) -> LLMResult:
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                "messages": [{"role": r, "content": t} for r, t in _merge(messages)]}
        try:
            r = httpx.post("https://api.anthropic.com/v1/messages", json=body, timeout=self.timeout,
                           headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            d = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(f"anthropic request failed: {type(e).__name__}") from None
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage", {})
        return LLMResult(text, u.get("input_tokens"), u.get("output_tokens"))


class GeminiClient:
    def __init__(self, model: str, key: str, timeout: float = 25):
        self.model, self.key, self.timeout = model, key, timeout

    def generate(self, system, messages, max_tokens) -> LLMResult:
        gen = {"maxOutputTokens": max_tokens, "temperature": 0, "responseMimeType": "application/json"}
        if "flash" in self.model:
            gen["thinkingConfig"] = {"thinkingBudget": 0}
        body = {"systemInstruction": {"parts": [{"text": system}]}, "generationConfig": gen,
                "contents": [{"role": "user" if r == "user" else "model", "parts": [{"text": t}]}
                             for r, t in _merge(messages)]}
        try:
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                           json=body, headers={"x-goog-api-key": self.key}, timeout=self.timeout)
            r.raise_for_status()
            d = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(f"gemini request failed: {type(e).__name__}") from None
        try:
            text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            text = ""
        u = d.get("usageMetadata", {})
        return LLMResult(text, u.get("promptTokenCount"), u.get("candidatesTokenCount"))


class OpenAIClient:
    def __init__(self, model: str, key: str, timeout: float = 25):
        self.model, self.key, self.timeout = model, key, timeout

    def generate(self, system, messages, max_tokens) -> LLMResult:
        body = {"model": self.model, "max_completion_tokens": max_tokens, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}] + [{"role": r, "content": t} for r, t in _merge(messages)]}
        try:
            r = httpx.post("https://api.openai.com/v1/chat/completions", json=body, timeout=self.timeout,
                           headers={"Authorization": f"Bearer {self.key}"})
            r.raise_for_status()
            d = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(f"openai request failed: {type(e).__name__}") from None
        try:
            text = d["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            text = ""
        u = d.get("usage", {})
        return LLMResult(text, u.get("prompt_tokens"), u.get("completion_tokens"))


def build_client(provider: str, model: str):
    key = key_for(provider)
    if not key:
        raise LLMError(f"no API key configured for provider '{provider}'")
    if provider == "anthropic":
        return AnthropicClient(model, key)
    if provider == "gemini":
        return GeminiClient(model, key)
    if provider == "openai":
        return OpenAIClient(model, key)
    raise LLMError(f"unknown provider '{provider}'")
