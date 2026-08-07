from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .config_manager import config
from .models import MessageContext


# ============================================================
# Константы
# ============================================================

INCOMING = "incoming"
OUTGOING = "outgoing"

# Каналы, которые реально существуют в PoE.
VALID_CHANNELS = {
    "global",
    "local",
    "trade",
    "party",
    "guild",
    "whisper",
}


# ============================================================
# RoutingDecision
# ============================================================


@dataclass(slots=True)
class RoutingDecision:
    """
    Результат работы TranslationRouter.

    Содержит всю информацию, необходимую следующему
    этапу Translation Pipeline.
    """

    # --------------------------------------------------------
    # Направление
    # --------------------------------------------------------

    direction: str

    # --------------------------------------------------------
    # Канал, для которого был выбран маршрут
    #
    # Для outgoing здесь будет "whisper",
    # поскольку исходящие используют маршрут Whisper.
    # --------------------------------------------------------

    channel: str

    # --------------------------------------------------------
    # Очередь провайдеров
    #
    # Порядок имеет значение:
    #
    # ["gemini", "openrouter", "google"]
    #
    # означает:
    #
    # 1. Gemini
    # 2. OpenRouter
    # 3. Google
    # --------------------------------------------------------

    providers: List[str]

    # --------------------------------------------------------
    # Языковое направление
    # --------------------------------------------------------

    source_language: Optional[str] = None
    target_language: Optional[str] = None

    # --------------------------------------------------------
    # Нужно ли вообще переводить сообщение
    #
    # False используется, например, когда локальный
    # детектор определил, что сообщение уже находится
    # на нужном языке.
    # --------------------------------------------------------

    should_translate: bool = True

    # --------------------------------------------------------
    # Причина, по которой перевод не требуется
    # --------------------------------------------------------

    skip_reason: Optional[str] = None


# ============================================================
# TranslationRouter
# ============================================================


class TranslationRouter:
    """
    Определяет маршрут перевода для MessageContext.

    Router НЕ выполняет перевод.

    Его задача:

        MessageContext
            ↓
        направление
            ↓
        канал
            ↓
        очередь провайдеров
            ↓
        языковое направление
            ↓
        RoutingDecision

    Пример:

        incoming Global
            →
        ["gemini", "google"]
            →
        en -> ru

    Исходящее сообщение:

        outgoing
            →
        маршрут Whisper
            →
        ["gemini", "google"]
            →
        ru -> en
    """

    # ========================================================
    # Основной метод
    # ========================================================

    def resolve(
        self,
        context: MessageContext,
    ) -> RoutingDecision:
        """
        Определяет маршрут для MessageContext.

        Пока Router не занимается детекцией языка.
        Предполагается, что решение о необходимости перевода
        будет приниматься TranslationManager перед вызовом
        Router либо отдельным LanguageDetector.

        Поэтому здесь should_translate по умолчанию True.
        """

        direction = self._resolve_direction(
            context,
        )

        channel = self._resolve_channel(
            context,
            direction,
        )

        providers = self._resolve_providers(
            channel,
        )

        source_language, target_language = self._resolve_languages(
            providers,
            direction,
        )

        return RoutingDecision(
            direction=direction,
            channel=channel,
            providers=providers,
            source_language=source_language,
            target_language=target_language,
            should_translate=True,
            skip_reason=None,
        )

    # ========================================================
    # Направление
    # ========================================================

    def _resolve_direction(
        self,
        context: MessageContext,
    ) -> str:
        """
        Определяет направление сообщения.

        ChatMessage.direction уже предусмотрен моделью:

            direction: Optional[str]

        Для входящих сообщений обычно direction отсутствует.

        Для исходящих ожидается:

            "outgoing"

        Дополнительно принимаем несколько очевидных вариантов,
        чтобы Router был устойчив к будущим изменениям LogParser.
        """

        direction = context.direction

        if direction is None:
            return INCOMING

        normalized = str(direction).strip().lower()

        if normalized in {
            "outgoing",
            "out",
            "send",
            "sent",
        }:
            return OUTGOING

        return INCOMING

    # ========================================================
    # Канал
    # ========================================================

    def _resolve_channel(
        self,
        context: MessageContext,
        direction: str,
    ) -> str:
        """
        Определяет канал, из которого берётся маршрут.

        Для входящих:

            channel = реальный канал сообщения.

        Для исходящих:

            channel = whisper

        Это соответствует нашей договорённости:

            Outgoing использует маршрут Whisper.

        Отдельный routing.outgoing не используется.
        """

        if direction == OUTGOING:
            return "whisper"

        channel = context.channel

        if not channel:
            return "global"

        normalized = str(channel).strip().lower()

        if normalized in VALID_CHANNELS:
            return normalized

        # Неизвестный канал отправляем в Global.
        #
        # Это безопаснее, чем пытаться обратиться
        # к произвольному ключу конфигурации.
        return "global"

    # ========================================================
    # Очередь провайдеров
    # ========================================================

    def _resolve_providers(
        self,
        channel: str,
    ) -> List[str]:
        """
        Получает очередь провайдеров из ConfigManager.

        Например:

            routing.whisper = [
                "gemini",
                "openrouter",
                "google",
            ]

        Router возвращает именно этот порядок.
        """

        providers = config.route(
            channel,
        )

        if not providers:
            return ["google"]

        # ----------------------------------------------------
        # Защита от повреждённого config.json
        # ----------------------------------------------------

        result: List[str] = []

        for provider_id in providers:
            if not isinstance(provider_id, str):
                continue

            provider_id = provider_id.strip().lower()

            if not provider_id:
                continue

            if provider_id not in result:
                result.append(provider_id)

        if not result:
            return ["google"]

        return result

    # ========================================================
    # Языки
    # ========================================================

    def _resolve_languages(
        self,
        providers: List[str],
        direction: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Определяет языковое направление.

        Важный момент:

        Настройки провайдера в config.json описывают
        направление ВХОДЯЩЕГО перевода.

        Например:

            source_language = "en"
            target_language = "ru"

        Для outgoing направление автоматически
        разворачивается:

            ru -> en

        Используется первый провайдер маршрута,
        поскольку именно он является первым кандидатом
        на перевод.

        Если первый провайдер не содержит языковых настроек,
        используются безопасные значения en -> ru.
        """

        if not providers:
            return None, None

        provider_id = providers[0]

        if direction == OUTGOING:
            return config.provider_outgoing_languages(
                provider_id,
            )

        return config.provider_languages(
            provider_id,
        )

    # ========================================================
    # Удобные публичные методы
    # ========================================================

    def route_for_context(
        self,
        context: MessageContext,
    ) -> List[str]:
        """
        Возвращает только очередь провайдеров.

        Удобный сокращённый вариант:

            router.route_for_context(context)
        """

        decision = self.resolve(
            context,
        )

        return decision.providers

    # --------------------------------------------------------

    def languages_for_context(
        self,
        context: MessageContext,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Возвращает языковое направление для сообщения.

        Например:

            ("en", "ru")

        или для outgoing:

            ("ru", "en")
        """

        decision = self.resolve(
            context,
        )

        return (
            decision.source_language,
            decision.target_language,
        )

    # --------------------------------------------------------

    def is_outgoing(
        self,
        context: MessageContext,
    ) -> bool:
        """
        Проверяет, является ли сообщение исходящим.
        """

        return self._resolve_direction(context) == OUTGOING

    # --------------------------------------------------------

    def is_incoming(
        self,
        context: MessageContext,
    ) -> bool:
        """
        Проверяет, является ли сообщение входящим.
        """

        return self._resolve_direction(context) == INCOMING


# ============================================================
# Standalone test
# ============================================================

if __name__ == "__main__":
    from .models import ChatMessage

    router = TranslationRouter()

    # --------------------------------------------------------
    # Incoming Global
    # --------------------------------------------------------

    incoming_global = ChatMessage(
        channel="global",
        channel_symbol="#",
        sender="Tester",
        text="WTB mirror",
        direction=None,
    )

    context = MessageContext.from_chat_message(
        incoming_global,
    )

    decision = router.resolve(
        context,
    )

    print("=== Incoming Global ===")
    print("direction:", decision.direction)
    print("channel:", decision.channel)
    print("providers:", decision.providers)
    print("languages:", decision.source_language, "->", decision.target_language)
    print()

    # --------------------------------------------------------
    # Incoming Local
    # --------------------------------------------------------

    incoming_local = ChatMessage(
        channel="local",
        channel_symbol="",
        sender="Tester",
        text="Selling Mageblood",
        direction=None,
    )

    context = MessageContext.from_chat_message(
        incoming_local,
    )

    decision = router.resolve(
        context,
    )

    print("=== Incoming Local ===")
    print("direction:", decision.direction)
    print("channel:", decision.channel)
    print("providers:", decision.providers)
    print("languages:", decision.source_language, "->", decision.target_language)
    print()

    # --------------------------------------------------------
    # Incoming Whisper
    # --------------------------------------------------------

    incoming_whisper = ChatMessage(
        channel="whisper",
        channel_symbol="",
        sender="Tester",
        text="Hi, are you selling this?",
        direction=None,
    )

    context = MessageContext.from_chat_message(
        incoming_whisper,
    )

    decision = router.resolve(
        context,
    )

    print("=== Incoming Whisper ===")
    print("direction:", decision.direction)
    print("channel:", decision.channel)
    print("providers:", decision.providers)
    print("languages:", decision.source_language, "->", decision.target_language)
    print()

    # --------------------------------------------------------
    # Outgoing
    # --------------------------------------------------------

    outgoing = ChatMessage(
        channel="global",
        channel_symbol="#",
        sender="Me",
        text="Куплю Mageblood",
        direction="outgoing",
    )

    context = MessageContext.from_chat_message(
        outgoing,
    )

    decision = router.resolve(
        context,
    )

    print("=== Outgoing ===")
    print("direction:", decision.direction)
    print("channel:", decision.channel)
    print("providers:", decision.providers)
    print("languages:", decision.source_language, "->", decision.target_language)
    print()
