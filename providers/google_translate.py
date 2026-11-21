from __future__ import annotations

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import httpx
from googletrans import Translator

from .base import BaseTranslator


class GoogleTranslateTranslator(BaseTranslator):
    """
    Google Translate client based on googletrans.

    Uses translate.googleapis.com without an API key or HTML parsing.
    """

    name = "Google Translate"

    REQUEST_TIMEOUT_SECONDS = 10
    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 1.0

    SERVICE_URLS = ["translate.googleapis.com"]

    def __init__(
        self,
        source_language: str = "auto",
        target_language: str = "ru",
    ):
        self.source_language = source_language
        self.target_language = target_language

        # Backward compatibility with the project's previous interface.
        self.source_lang = source_language
        self.target_lang = target_language

    @staticmethod
    def _get_http_status(error: Exception) -> Optional[int]:
        """Extract an HTTP status code from a googletrans/httpx exception."""

        status = getattr(error, "status_code", None)
        if status is not None:
            try:
                return int(status)
            except (TypeError, ValueError):
                pass

        response = getattr(error, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
            if status is not None:
                try:
                    return int(status)
                except (TypeError, ValueError):
                    pass

        match = re.search(
            r'(?:status code|HTTP)\s*["\']?(\d{3})',
            str(error),
            re.IGNORECASE,
        )
        if match:
            return int(match.group(1))

        return None

    @staticmethod
    def _run_async(coroutine):
        """Run googletrans' async API from the provider's sync interface."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        # If the caller already has an event loop, run this coroutine in
        # a separate thread with its own loop rather than nesting asyncio.run().
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coroutine)
            return future.result()

    async def _translate_async(
        self,
        text: str,
        source: str,
        target: str,
    ) -> str:
        async with Translator(
            service_urls=self.SERVICE_URLS,
            raise_exception=True,
            timeout=self.REQUEST_TIMEOUT_SECONDS,
        ) as translator:
            result = await translator.translate(
                text,
                src=source,
                dest=target,
            )

        translated_text = str(result.text or "")
        if not translated_text.strip():
            raise RuntimeError(
                "Google Translate returned an empty translation"
            )

        return translated_text

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
            raise ValueError(
                "Google Translate input exceeds 5000 characters"
            )

        src = source_language or self.source_language
        dst = target_language or self.target_language

        if src == dst:
            return text

        last_error: Optional[Exception] = None

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                return self._run_async(
                    self._translate_async(
                        text=text,
                        source=src,
                        target=dst,
                    )
                )

            except Exception as exc:
                last_error = exc
                status = self._get_http_status(exc)

                # Do not immediately repeat requests while Google is rate-limiting.
                if status == 429:
                    raise RuntimeError(
                        "Google Translate HTTP 429: Too Many Requests. "
                        "Wait before sending new requests."
                    ) from exc

                retryable = (
                    isinstance(exc, httpx.TransportError)
                    or status in (408, 500, 502, 503, 504)
                )

                if not retryable or attempt == self.MAX_ATTEMPTS:
                    break

                time.sleep(self.RETRY_DELAY_SECONDS * attempt)

        raise RuntimeError(
            f"Google Translate failed after {attempt} attempts: {last_error}"
        ) from last_error
