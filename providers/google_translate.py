from __future__ import annotations

from typing import Optional

from deep_translator import GoogleTranslator

from .base import BaseTranslator


class GoogleTranslateTranslator(BaseTranslator):
    """
    Переводчик на основе deep-translator.

    Не требует API-ключа.
    Использует веб-интерфейс Google Translate.

    Документация:
        https://pypi.org/project/deep-translator/
    """

    name = "Google Translate"

    def __init__(
        self,
        source_lang: str = "auto",
        target_lang: str = "ru",
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang

        self._translator = GoogleTranslator(
            source=self.source_lang,
            target=self.target_lang,
        )

    # ---------------------------------------------------------

    def translate(
        self,
        text: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
    ) -> str:

        if not text:
            return ""

        # Если языки отличаются от текущих —
        # создаем временный экземпляр переводчика.

        src = source_lang or self.source_lang
        dst = target_lang or self.target_lang

        if src != self.source_lang or dst != self.target_lang:
            translator = GoogleTranslator(
                source=src,
                target=dst,
            )
            return translator.translate(text)

        return self._translator.translate(text)
