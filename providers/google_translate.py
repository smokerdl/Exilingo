from __future__ import annotations

import time
from typing import Optional

import requests
from bs4 import BeautifulSoup
from deep_translator.constants import BASE_URLS

from .base import BaseTranslator


class GoogleTranslateTranslator(BaseTranslator):
    """
    Переводчик на основе веб-интерфейса Google Translate.

    API-ключ не требуется. Запрос выполняется напрямую через requests,
    чтобы не зависеть от хрупкого HTML-парсинга внутри deep-translator
    и чтобы мы могли задавать User-Agent и управлять повторными попытками.
    """

    name = "Google Translate"

    REQUEST_TIMEOUT_SECONDS = 10
    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 0.8

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        source_language: str = "auto",
        target_language: str = "ru",
    ):
        self.source_language = source_language
        self.target_language = target_language

        # Совместимость со старым кодом проекта.
        self.source_lang = source_language
        self.target_lang = target_language

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def translate(
        self,
        text: str,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
    ) -> str:
        if not text:
            return ""

        text = str(text).strip()
        if not text:
            return ""

        if len(text) > 5000:
            raise ValueError("Google Translate input exceeds 5000 characters")

        src = source_language or self.source_language
        dst = target_language or self.target_language

        if src == dst:
            return text

        params = {
            "sl": src,
            "tl": dst,
            "q": text,
        }

        url = BASE_URLS.get("GOOGLE_TRANSLATE")
        if not url:
            raise RuntimeError("Google Translate endpoint is not configured")

        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")
                element = soup.find("div", {"class": "t0"})

                if element is None:
                    element = soup.find(
                        "div",
                        {"class": "result-container"},
                    )

                if element is not None:
                    result = element.get_text(strip=True)
                    if result and result != text:
                        return result

                last_error = RuntimeError(
                    "Google Translate response did not contain a translation"
                )

            except requests.RequestException as exc:
                last_error = exc

            if attempt < self.MAX_ATTEMPTS:
                time.sleep(self.RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(
            f"Google Translate failed after {self.MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error
