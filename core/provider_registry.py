from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Optional

from providers.base import BaseTranslator
from providers.google_translate import GoogleTranslateTranslator
from providers.gemini import GeminiTranslator
from providers.groq import GroqTranslator
from providers.openrouter import OpenRouterTranslator
from providers.ollama import OllamaTranslator

from .config_manager import config


@dataclass(slots=True)
class ProviderInfo:
    """Описание зарегистрированного переводчика."""

    id: str
    name: str
    configured: bool
    enabled: bool
    requires_api_key: bool


class ProviderRegistry:
    """
    Единая точка регистрации всех переводчиков Exilingo.

    Registry отвечает за список поддерживаемых провайдеров, их текущее
    состояние и создание экземпляров переводчиков. TranslationManager
    и GUI не создают конкретные провайдеры напрямую.
    """

    def __init__(self):
        self._providers = {
            "google": {
                "name": "Google Translate",
                "factory": self._create_google,
                "requires_api_key": False,
            },
            "gemini": {
                "name": "Gemini",
                "factory": self._create_gemini,
                "requires_api_key": True,
            },
            "groq": {
                "name": "Groq",
                "factory": self._create_groq,
                "requires_api_key": True,
            },
            "openrouter": {
                "name": "OpenRouter",
                "factory": self._create_openrouter,
                "requires_api_key": True,
            },
            "ollama": {
                "name": "Ollama",
                "factory": self._create_ollama,
                "requires_api_key": False,
            },
        }
        self._instances: dict[tuple[str, str, str, str], BaseTranslator] = {}

    def _is_configured(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        return provider is not None and provider["factory"] is not None

    def _is_enabled(self, provider_id: str) -> bool:
        return config.provider_enabled(provider_id)

    def is_available(self, provider_id: str) -> bool:
        return (
            provider_id in self._providers
            and self._is_configured(provider_id)
            and self._is_enabled(provider_id)
        )

    def _settings_fingerprint(self, provider_id: str, source_language: str, target_language: str) -> str:
        provider = config.get_provider(provider_id)
        settings = {key: value for key, value in provider.items() if key not in {"api_key", "enabled"}}
        api_key = config.provider_api_key(provider_id)
        if api_key:
            settings["api_key_sha256"] = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        payload = {
            "source_language": source_language,
            "target_language": target_language,
            "settings": settings,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    def _create_google(self, source_language: Optional[str] = None, target_language: Optional[str] = None) -> BaseTranslator:
        if source_language is None or target_language is None:
            source_language, target_language = config.provider_languages("google")
        return GoogleTranslateTranslator(source_language=source_language, target_language=target_language)

    def _create_gemini(self, source_language: Optional[str] = None, target_language: Optional[str] = None) -> BaseTranslator:
        provider = config.get("providers", "gemini") or {}
        api_key = config.provider_api_key("gemini")
        model = str(provider.get("model", "gemini-3.5-flash-lite")).strip()
        system_prompt = str(provider.get("system_prompt", "")).strip()
        if source_language is None:
            source_language = provider.get("source_language", "en")
        if target_language is None:
            target_language = provider.get("target_language", "ru")
        return GeminiTranslator(api_key=api_key, model=model or "gemini-3.5-flash-lite", system_prompt=system_prompt, source_language=str(source_language), target_language=str(target_language))

    def _create_groq(self, source_language: Optional[str] = None, target_language: Optional[str] = None) -> BaseTranslator:
        provider = config.get("providers", "groq") or {}
        api_key = config.provider_api_key("groq")
        model = str(provider.get("model", "openai/gpt-oss-20b")).strip()
        system_prompt = str(provider.get("system_prompt", "")).strip()
        if source_language is None:
            source_language = provider.get("source_language", "en")
        if target_language is None:
            target_language = provider.get("target_language", "ru")
        return GroqTranslator(api_key=api_key, model=model or "openai/gpt-oss-20b", system_prompt=system_prompt, source_language=str(source_language), target_language=str(target_language))

    def _create_openrouter(self, source_language: Optional[str] = None, target_language: Optional[str] = None) -> BaseTranslator:
        provider = config.get("providers", "openrouter") or {}
        api_key = config.provider_api_key("openrouter")
        model = str(provider.get("model", "gemma-4-26b-a4b-it:free")).strip()
        system_prompt = str(provider.get("system_prompt", "")).strip()
        if source_language is None:
            source_language = provider.get("source_language", "en")
        if target_language is None:
            target_language = provider.get("target_language", "ru")
        return OpenRouterTranslator(api_key=api_key, model=model or "gemma-4-26b-a4b-it:free", system_prompt=system_prompt, source_language=str(source_language), target_language=str(target_language))

    def _create_ollama(self, source_language: Optional[str] = None, target_language: Optional[str] = None) -> BaseTranslator:
        provider = config.get("providers", "ollama") or {}
        host = str(provider.get("host", "http://127.0.0.1:11434")).strip()
        model = str(provider.get("model", "")).strip()
        system_prompt = str(provider.get("system_prompt", "")).strip()
        if source_language is None:
            source_language = provider.get("source_language", "en")
        if target_language is None:
            target_language = provider.get("target_language", "ru")
        return OllamaTranslator(host=host or "http://127.0.0.1:11434", model=model, system_prompt=system_prompt, source_language=str(source_language), target_language=str(target_language))

    def create(self, provider_id: str, source_language: Optional[str] = None, target_language: Optional[str] = None, require_enabled: bool = True) -> BaseTranslator:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError(f"Неизвестный провайдер: {provider_id}")
        if require_enabled and not self.is_available(provider_id):
            if not self._is_configured(provider_id):
                raise NotImplementedError(f"Провайдер '{provider_id}' пока не реализован.")
            raise RuntimeError(f"Провайдер '{provider_id}' выключен или не настроен.")
        factory: Callable = provider["factory"]
        if factory is None:
            raise NotImplementedError(f"Провайдер '{provider_id}' пока не реализован.")

        effective_source, effective_target = config.provider_languages(provider_id)
        source_language = source_language or effective_source
        target_language = target_language or effective_target
        key = (
            provider_id,
            str(source_language),
            str(target_language),
            self._settings_fingerprint(provider_id, str(source_language), str(target_language)),
        )
        cached = self._instances.get(key)
        if cached is not None:
            return cached

        instance = factory(source_language=source_language, target_language=target_language)
        self._instances[key] = instance
        return instance

    def clear_cache(self, provider_id: Optional[str] = None) -> None:
        """Удаляет кэшированные экземпляры; при необходимости только одного провайдера."""
        if provider_id is None:
            self._instances.clear()
            return
        for key in [key for key in self._instances if key[0] == provider_id]:
            self._instances.pop(key, None)

    def provider_info(self, provider_id: str) -> ProviderInfo:
        provider = self._providers[provider_id]
        return ProviderInfo(id=provider_id, name=provider["name"], configured=self._is_configured(provider_id), enabled=self._is_enabled(provider_id), requires_api_key=provider["requires_api_key"])

    def providers(self) -> list[ProviderInfo]:
        return [self.provider_info(provider_id) for provider_id in self._providers]

    def active_providers(self) -> list[ProviderInfo]:
        return [provider for provider in self.providers() if provider.enabled and provider.configured]

    def exists(self, provider_id: str) -> bool:
        return provider_id in self._providers
