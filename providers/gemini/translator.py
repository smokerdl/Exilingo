from __future__ import annotations

from typing import Optional

from ..base import BaseTranslator


class GeminiTranslator(BaseTranslator):
    """
    Переводчик на основе официального Google GenAI SDK.

    Требует Gemini API key. Модель и system prompt задаются при создании
    экземпляра и могут быть изменены настройками проекта.
    """

    name = "Gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        system_prompt: str = (
            "You are a translator of the Path of Exile game chat. "
            "Translate naturally without explanations. Return only the translation."
        ),
        source_language: str = "en",
        target_language: str = "ru",
    ):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.source_language = source_language
        self.target_language = target_language

        # Compatibility with the naming used by older providers.
        self.source_lang = source_language
        self.target_lang = target_language

        if not self.api_key:
            raise ValueError("Gemini API key is required")

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ImportError(
                "Gemini provider requires the 'google-genai' package. "
                "Install it with: pip install google-genai"
            ) from exc

        self._types = types
        self._client = genai.Client(api_key=self.api_key)

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

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=self.system_prompt,
            ),
        )

        result = getattr(response, "text", None)
        if result is None:
            raise RuntimeError("Gemini returned an empty response")

        result = result.strip()
        if not result:
            raise RuntimeError("Gemini returned an empty translation")

        return result
