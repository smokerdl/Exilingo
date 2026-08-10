from __future__ import annotations

from typing import Optional

import httpx

from ..base import BaseTranslator


class OllamaTranslator(BaseTranslator):
    """Translator backed by Ollama's local HTTP API."""

    name = "Ollama"
    REQUEST_TIMEOUT_MS = 60_000
    DEFAULT_HOST = "http://127.0.0.1:11434"

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        model: str = "",
        system_prompt: str = (
            "You are a translator of the Path of Exile game chat. "
            "Translate naturally without explanations. Return only the translation."
        ),
        source_language: str = "en",
        target_language: str = "ru",
    ):
        self.host = str(host or self.DEFAULT_HOST).strip().rstrip("/")
        self.model = str(model or "").strip()
        self.system_prompt = str(system_prompt or "").strip()
        self.source_language = str(source_language or "en").strip() or "en"
        self.target_language = str(target_language or "ru").strip() or "ru"

        self.source_lang = self.source_language
        self.target_lang = self.target_language

        if not self.model:
            raise ValueError("Ollama model is required")

    @property
    def API_URL(self) -> str:
        return f"{self.host}/api/chat"

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
            headers={"Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                },
            },
            timeout=self.REQUEST_TIMEOUT_MS / 1000,
        )
        response.raise_for_status()

        payload = response.json()
        message = payload.get("message") or {}
        result = message.get("content")

        if result is None:
            raise RuntimeError("Ollama returned an empty response")

        result = str(result).strip()
        if not result:
            raise RuntimeError("Ollama returned an empty translation")

        return result
