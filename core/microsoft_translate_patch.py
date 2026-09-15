from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

import httpx

from core.config_manager import DEFAULT_CONFIG, config
from core.provider_registry import ProviderRegistry
from providers.base import BaseTranslator


MICROSOFT_PROVIDER_ID = "microsoft"
MICROSOFT_PROVIDER_NAME = "Microsoft Translator"
MICROSOFT_API_VERSION = "2026-06-06"
MICROSOFT_DEFAULT_ENDPOINT = "https://api.cognitive.microsofttranslator.com"


class MicrosoftTranslateTranslator(BaseTranslator):
    """Microsoft Azure Translator Text API client."""

    def __init__(
        self,
        api_key: str,
        source_language: str = "en",
        target_language: str = "ru",
        endpoint: str = MICROSOFT_DEFAULT_ENDPOINT,
        region: str = "",
        timeout: float = 10.0,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.source_language = str(source_language or "en").strip() or "en"
        self.target_language = str(target_language or "ru").strip() or "ru"
        self.endpoint = str(endpoint or MICROSOFT_DEFAULT_ENDPOINT).strip().rstrip("/")
        self.region = str(region or "").strip()
        self.timeout = float(timeout)
        self._session = httpx.Client(timeout=self.timeout)

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        text = str(text or "")
        if not text.strip():
            return ""
        if not self.api_key:
            raise RuntimeError("Microsoft Translator API key is not configured.")

        source = str(source_language or self.source_language).strip() or self.source_language
        target = str(target_language or self.target_language).strip() or self.target_language
        if source.lower() == "auto":
            raise RuntimeError("Microsoft Translator requires an explicit source language.")

        url = f"{self.endpoint}/translate"
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.region:
            headers["Ocp-Apim-Subscription-Region"] = self.region

        payload = {
            "inputs": [
                {
                    "text": text,
                    "language": source,
                    "targets": [{"language": target}],
                }
            ]
        }

        try:
            response = self._session.post(
                url,
                params={"api-version": MICROSOFT_API_VERSION},
                headers=headers,
                json=payload,
            )
        except httpx.RequestError as exc:
            raise RuntimeError(f"Microsoft Translator request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()
            if len(detail) > 500:
                detail = detail[:500] + "..."
            raise RuntimeError(
                f"Microsoft Translator HTTP {response.status_code}"
                + (f": {detail}" if detail else "")
            )

        try:
            payload = response.json()
            value = payload.get("value") or []
            translations = value[0].get("translations") if value else None
            translation = translations[0].get("text") if translations else None
        except (ValueError, TypeError, AttributeError, IndexError) as exc:
            raise RuntimeError("Microsoft Translator returned an invalid response.") from exc

        if translation is None:
            raise RuntimeError("Microsoft Translator returned no translation.")
        return str(translation)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass


def _provider_api_key(provider_id: str) -> str:
    if provider_id == MICROSOFT_PROVIDER_ID:
        return config.secrets.get("microsoft_api_key")
    return config.provider_api_key(provider_id)


def _set_provider_api_key(provider_id: str, api_key: str) -> None:
    if provider_id == MICROSOFT_PROVIDER_ID:
        config.secrets.set("microsoft_api_key", str(api_key or "").strip())
        return
    config.set_provider_api_key(provider_id, api_key)


def _create_microsoft(
    self: ProviderRegistry,
    source_language: Optional[str] = None,
    target_language: Optional[str] = None,
) -> BaseTranslator:
    provider = config.get_provider(MICROSOFT_PROVIDER_ID)
    source_language = source_language or provider.get("source_language", "en")
    target_language = target_language or provider.get("target_language", "ru")
    api_key = _provider_api_key(MICROSOFT_PROVIDER_ID)
    endpoint = str(provider.get("endpoint", MICROSOFT_DEFAULT_ENDPOINT) or MICROSOFT_DEFAULT_ENDPOINT).strip()
    region = str(provider.get("region", "") or "").strip()
    timeout = float(provider.get("timeout", 10.0) or 10.0)
    return MicrosoftTranslateTranslator(
        api_key=api_key,
        source_language=str(source_language),
        target_language=str(target_language),
        endpoint=endpoint,
        region=region,
        timeout=timeout,
    )


def _install_config_support() -> None:
    DEFAULT_CONFIG["providers"].setdefault(
        MICROSOFT_PROVIDER_ID,
        {
            "enabled": False,
            "source_language": "en",
            "target_language": "ru",
            "endpoint": MICROSOFT_DEFAULT_ENDPOINT,
            "region": "",
            "timeout": 10.0,
        },
    )

    provider = config.data.setdefault("providers", {}).setdefault(
        MICROSOFT_PROVIDER_ID,
        dict(DEFAULT_CONFIG["providers"][MICROSOFT_PROVIDER_ID]),
    )
    if not isinstance(provider, dict):
        config.data["providers"][MICROSOFT_PROVIDER_ID] = dict(
            DEFAULT_CONFIG["providers"][MICROSOFT_PROVIDER_ID]
        )
        provider = config.data["providers"][MICROSOFT_PROVIDER_ID]

    defaults = DEFAULT_CONFIG["providers"][MICROSOFT_PROVIDER_ID]
    provider.setdefault("enabled", defaults["enabled"])
    provider.setdefault("source_language", defaults["source_language"])
    provider.setdefault("target_language", defaults["target_language"])
    provider.setdefault("endpoint", defaults["endpoint"])
    provider.setdefault("region", defaults["region"])
    provider.setdefault("timeout", defaults["timeout"])


def _install_registry_support() -> None:
    if getattr(ProviderRegistry, "_microsoft_translate_patch_installed", False):
        return

    original_init = ProviderRegistry.__init__
    ProviderRegistry._create_microsoft = _create_microsoft

    def patched_init(self: ProviderRegistry, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._providers[MICROSOFT_PROVIDER_ID] = {
            "name": MICROSOFT_PROVIDER_NAME,
            "factory": self._create_microsoft,
            "requires_api_key": True,
        }

    ProviderRegistry.__init__ = patched_init
    ProviderRegistry._microsoft_translate_patch_installed = True


_install_config_support()
_install_registry_support()

__all__ = ["MicrosoftTranslateTranslator"]
