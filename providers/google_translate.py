from __future__ import annotations

from typing import Optional

from deep_translator import GoogleTranslator

from .base import BaseTranslator


class GoogleTranslateTranslator(BaseTranslator):
    """
    Переводчик на основе deep-translator.

    Не требует API-ключа.
    Использует веб-интерфейс Google Translate.
    """

    name = "Google Translate"

    def __init__(
        self,
        source_language: str = "auto",
        target_language: str = "ru",
    ):
        # Новые имена параметров
        self.source_language = source_language
        self.target_language = target_language

        # Совместимость со старым кодом проекта
        self.source_lang = source_language
        self.target_lang = target_language

        self._translator = GoogleTranslator(
            source=self.source_language,
            target=self.target_language,
        )

    # ---------------------------------------------------------

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

        #
        # Если язык изменился — используем временный экземпляр.
        #
        if src != self.source_language or dst != self.target_language:
            translator = GoogleTranslator(
                source=src,
                target=dst,
            )
            return translator.translate(text)

        return self._translator.translate(text)
