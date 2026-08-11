from __future__ import annotations

from typing import Optional

import httpx

from ..base import BaseTranslator


class GroqTranslator(BaseTranslator):
    """Translator backed by Groq's OpenAI-compatible chat completions API."""

    name = "Groq"
    REQUEST_TIMEOUT_MS = 15_000
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-oss-20b",
        system_prompt: str = (
            "You are a translator of the Path of Exile game chat. "
            "Translate naturally without explanations. Return only the translation."
        ),
        source_language: str = "en",
        target_language: str = "ru",
    ):
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "openai/gpt-oss-20b").strip() or "openai/gpt-oss-20b"
        self.system_prompt = str(system_prompt or "").strip()
        self.source_language = str(source_language or "en").strip() or "en"
        self.target_language = str(target_language or "ru").strip() or "ru"

        self.source_lang = self.source_language
        self.target_lang = self.target_language

        if not self.api_key:
            raise ValueError("Groq API key is required")

    def translate(
        self,
        text: str,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
    ) -> str:
        if not text:
            return ""

        src = source_language or self.source_language
        dst = target_language or self.target_language

        prompt = (
            f"Translate the following Path of Exile game-chat message from "
            f"{src} to {dst}. Preserve player names, item names, game terms, "
            f"numbers, symbols and formatting whenever appropriate. "
            f"Return only the translated text.\n\n"
            f"{text}"
        )

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = httpx.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.2,
            },
            timeout=self.REQUEST_TIMEOUT_MS / 1000,
        )
        response.raise_for_status()

        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("Groq returned no choices")

        message = choices[0].get("message") or {}
        result = message.get("content")

        if result is None:
            raise RuntimeError("Groq returned an empty response")

        result = str(result).strip()
        if not result:
            raise RuntimeError("Groq returned an empty translation")

        return result
