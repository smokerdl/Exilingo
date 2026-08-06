from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from providers.base import BaseTranslator
from providers.google_translate import GoogleTranslateTranslator


# ==========================================================
# Информация о провайдере
# ==========================================================


@dataclass(slots=True)
class ProviderInfo:
    """
    Описание зарегистрированного переводчика.

    Используется GUI, маршрутизатором и
    системой настроек.
    """

    id: str
    name: str

    configured: bool
    enabled: bool

    requires_api_key: bool


# ==========================================================
# Registry
# ==========================================================


class ProviderRegistry:
    """
    Единая точка регистрации всех переводчиков Exilingo.

    GUI никогда не создает переводчики самостоятельно.

    Он обращается только к ProviderRegistry.
    """

    def __init__(self):

        #
        # Пока список фиксированный.
        #
        # Позже информация будет
        # подтягиваться из config.json.
        #

        self._providers = {
            "google": {
                "name": "Google Translate",
                "factory": self._create_google,
                "configured": True,
                "enabled": True,
                "requires_api_key": False,
            },
            "gemini": {
                "name": "Gemini",
                "factory": None,
                "configured": False,
                "enabled": False,
                "requires_api_key": True,
            },
            "groq": {
                "name": "Groq",
                "factory": None,
                "configured": False,
                "enabled": False,
                "requires_api_key": True,
            },
            "openrouter": {
                "name": "OpenRouter",
                "factory": None,
                "configured": False,
                "enabled": False,
                "requires_api_key": True,
            },
            "ollama": {
                "name": "Ollama",
                "factory": None,
                "configured": False,
                "enabled": False,
                "requires_api_key": False,
            },
        }

    # ======================================================
    # Factory
    # ======================================================

    def _create_google(self) -> BaseTranslator:

        return GoogleTranslateTranslator(
            source_language="en",
            target_language="ru",
        )

    # ======================================================
    # Получить экземпляр переводчика
    # ======================================================

    def create(self, provider_id: str) -> BaseTranslator:

        provider = self._providers.get(provider_id)

        if provider is None:
            raise ValueError(f"Неизвестный провайдер: {provider_id}")

        factory: Callable | None = provider["factory"]

        if factory is None:
            raise NotImplementedError(f"Провайдер '{provider_id}' пока не реализован.")

        return factory()

    # ======================================================
    # Получить информацию
    # ======================================================

    def provider_info(self, provider_id: str) -> ProviderInfo:

        provider = self._providers[provider_id]

        return ProviderInfo(
            id=provider_id,
            name=provider["name"],
            configured=provider["configured"],
            enabled=provider["enabled"],
            requires_api_key=provider["requires_api_key"],
        )

    # ======================================================
    # Все провайдеры
    # ======================================================

    def providers(self) -> list[ProviderInfo]:

        result = []

        for provider_id in self._providers:
            result.append(self.provider_info(provider_id))

        return result

    # ======================================================
    # Только активные
    # ======================================================

    def active_providers(self) -> list[ProviderInfo]:

        return [p for p in self.providers() if p.enabled and p.configured]

    # ======================================================
    # Проверка существования
    # ======================================================

    def exists(self, provider_id: str) -> bool:

        return provider_id in self._providers
