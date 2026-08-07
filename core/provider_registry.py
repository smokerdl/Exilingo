from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from providers.base import BaseTranslator
from providers.google_translate import GoogleTranslateTranslator

from .config_manager import config


# ==========================================================
# Информация о провайдере
# ==========================================================


@dataclass(slots=True)
class ProviderInfo:
    """
    Описание зарегистрированного переводчика.

    Состояние configured/enabled берется из текущей конфигурации,
    поэтому GUI и Translation Pipeline видят одну и ту же картину.
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

    Registry отвечает за:

    - список поддерживаемых провайдеров;
    - проверку их текущей конфигурации;
    - создание экземпляра конкретного переводчика;
    - передачу языкового направления переводчику.

    GUI и TranslationManager не должны создавать конкретные
    переводчики напрямую.
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
                "factory": None,
                "requires_api_key": True,
            },
            "groq": {
                "name": "Groq",
                "factory": None,
                "requires_api_key": True,
            },
            "openrouter": {
                "name": "OpenRouter",
                "factory": None,
                "requires_api_key": True,
            },
            "ollama": {
                "name": "Ollama",
                "factory": None,
                "requires_api_key": False,
            },
        }

    # ======================================================
    # Состояние провайдера
    # ======================================================

    def _is_configured(self, provider_id: str) -> bool:
        """
        Возвращает True, если провайдер имеет минимально
        необходимые настройки для создания.

        Пока реализован только Google Translate.
        Для будущих AI-провайдеров configured станет True
        после добавления соответствующих фабрик.
        """
        provider = self._providers.get(provider_id)

        if provider is None:
            return False

        return provider["factory"] is not None

    # ------------------------------------------------------

    def _is_enabled(self, provider_id: str) -> bool:
        """Проверяет флаг enabled в config.json."""
        return config.provider_enabled(provider_id)

    # ------------------------------------------------------

    def is_available(self, provider_id: str) -> bool:
        """
        Провайдер можно использовать в Translation Pipeline,
        если он существует, реализован, настроен и включен.
        """
        return (
            provider_id in self._providers
            and self._is_configured(provider_id)
            and self._is_enabled(provider_id)
        )

    # ======================================================
    # Factory
    # ======================================================

    def _create_google(
        self,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
    ) -> BaseTranslator:
        """
        Создает Google Translate с заданным направлением.

        Если языки не переданы, используются настройки
        входящего перевода из config.json.
        """
        if source_language is None or target_language is None:
            source_language, target_language = config.provider_languages("google")

        return GoogleTranslateTranslator(
            source_language=source_language,
            target_language=target_language,
        )

    # ======================================================
    # Получить экземпляр переводчика
    # ======================================================

    def create(
        self,
        provider_id: str,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        require_enabled: bool = True,
    ) -> BaseTranslator:
        """
        Создает экземпляр провайдера.

        source_language/target_language позволяют TranslationManager
        передать конкретное направление:

            incoming: en -> ru
            outgoing: ru -> en

        require_enabled=True защищает от использования выключенного
        провайдера. Для старого кода можно отключить эту проверку.
        """
        provider = self._providers.get(provider_id)

        if provider is None:
            raise ValueError(f"Неизвестный провайдер: {provider_id}")

        if require_enabled and not self.is_available(provider_id):
            if not self._is_configured(provider_id):
                raise NotImplementedError(
                    f"Провайдер '{provider_id}' пока не реализован."
                )

            raise RuntimeError(
                f"Провайдер '{provider_id}' выключен или не настроен."
            )

        factory: Callable = provider["factory"]

        if factory is None:
            raise NotImplementedError(
                f"Провайдер '{provider_id}' пока не реализован."
            )

        if provider_id == "google":
            return factory(
                source_language=source_language,
                target_language=target_language,
            )

        return factory()

    # ======================================================
    # Получить информацию
    # ======================================================

    def provider_info(self, provider_id: str) -> ProviderInfo:
        provider = self._providers[provider_id]

        return ProviderInfo(
            id=provider_id,
            name=provider["name"],
            configured=self._is_configured(provider_id),
            enabled=self._is_enabled(provider_id),
            requires_api_key=provider["requires_api_key"],
        )

    # ======================================================
    # Все провайдеры
    # ======================================================

    def providers(self) -> list[ProviderInfo]:
        return [
            self.provider_info(provider_id)
            for provider_id in self._providers
        ]

    # ======================================================
    # Только активные
    # ======================================================

    def active_providers(self) -> list[ProviderInfo]:
        return [
            provider
            for provider in self.providers()
            if provider.enabled and provider.configured
        ]

    # ======================================================
    # Проверка существования
    # ======================================================

    def exists(self, provider_id: str) -> bool:
        return provider_id in self._providers
