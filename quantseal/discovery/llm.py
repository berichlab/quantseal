"""Unified BYOK LLM provider interface (OpenAI, Anthropic, Gemini, OpenAI-compatible / Ollama).

Uses pure `httpx` with zero vendor SDK bloat so self-hosted Docker containers
stay lean and secure. Includes mandatory secret redaction for audit logs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

_SECRET_PATTERNS = (
    re.compile(r"(AIza[0-9A-Za-z\-_]{20,})"),
    re.compile(r"(sk-[0-9A-Za-z\-_]{16,})"),
    re.compile(r"(Bearer\s+[0-9A-Za-z\-_\.]{12,})", re.IGNORECASE),
    re.compile(r"(x-api-key[\"']?\s*[:=]\s*[\"']?[0-9A-Za-z\-_]{12,})", re.IGNORECASE),
)


def sanitize_text_no_secrets(text: str | None, *, max_len: int = 131072) -> str:
    if not text:
        return ""
    cleaned = str(text)
    for pat in _SECRET_PATTERNS:
        cleaned = pat.sub("[REDACTED_SECRET]", cleaned)
    return cleaned[:max_len]


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "none"          # none | openai | anthropic | gemini | openai_compatible
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: float = 60.0

    def is_configured(self) -> bool:
        prov = self.provider.strip().lower()
        if prov in ("", "none", "disabled"):
            return False
        if prov == "openai_compatible" and self.base_url.strip():
            # Local servers like Ollama may not require an API key
            return True
        return bool(self.api_key.strip())


def complete_text(prompt: str, config: LLMConfig, *, system: str = "") -> dict[str, Any]:
    """Execute one completion request against the configured BYOK provider."""
    prov = config.provider.strip().lower()
    if not config.is_configured():
        raise RuntimeError("LLM provider is not configured")

    with httpx.Client(timeout=config.timeout_seconds) as client:
        if prov in ("openai", "openai_compatible"):
            base = config.base_url.strip().rstrip("/") or "https://api.openai.com/v1"
            url = f"{base}/chat/completions"
            headers = {"Content-Type": "application/json"}
            if config.api_key.strip():
                headers["Authorization"] = f"Bearer {config.api_key.strip()}"
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            body = {
                "model": config.model,
                "messages": messages,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
            }
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return {
                "provider": prov,
                "model": config.model,
                "text": text,
                "usage": data.get("usage") or {},
            }

        if prov == "anthropic":
            base = config.base_url.strip().rstrip("/") or "https://api.anthropic.com"
            url = f"{base}/v1/messages"
            headers = {
                "Content-Type": "application/json",
                "x-api-key": config.api_key.strip(),
                "anthropic-version": "2023-06-01",
            }
            body: dict[str, Any] = {
                "model": config.model,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                body["system"] = system
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            blocks = data.get("content") or []
            text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return {
                "provider": prov,
                "model": config.model,
                "text": text,
                "usage": data.get("usage") or {},
            }

        if prov == "gemini":
            base = config.base_url.strip().rstrip("/") or "https://generativelanguage.googleapis.com"
            url = f"{base}/v1beta/models/{config.model}:generateContent"
            params = {"key": config.api_key.strip()}
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            body = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "temperature": config.temperature,
                    "maxOutputTokens": config.max_tokens,
                },
            }
            resp = client.post(url, params=params, json=body)
            resp.raise_for_status()
            data = resp.json()
            cands = data.get("candidates") or []
            parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
            text = "\n".join(p.get("text", "") for p in parts)
            return {
                "provider": prov,
                "model": config.model,
                "text": text,
                "usage": data.get("usageMetadata") or {},
            }

    raise ValueError(f"Unsupported LLM provider '{config.provider}'")
