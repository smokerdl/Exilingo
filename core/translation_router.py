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
    """Результат работы TranslationRouter."""

    direction: str
    channel: str
    providers: List[str]
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    should_translate: bool = True
    skip_reason: Optional[str] = None


# ============================================================
# TranslationRouter
# ============================================================

class TranslationRouter:
    """
    Определяет направление, канал, очередь провайдеров
    и языковое направление для MessageContext.

    Router не выполняет перевод.
    """

    def resolve(self, context: MessageContext) -> RoutingDecision:
        direction = self._resolve_direction(context)
        channel = self._resolve_channel(context, direction)
        providers = self._resolve_providers(channel)
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

    def _resolve_direction(self, context: MessageContext) -> str:
        """
        Определяет направление сообщения.

        LogParser использует значения From/To.
        Дополнительно поддерживаем внутренние значения
        incoming/outgoing и их очевидные варианты.
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
            "to",
            "кому",
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
        Для incoming используется реальный канал.
        Для outgoing используется маршрут Whisper.
        """
        if direction == OUTGOING:
            return "whisper"

        channel = context.channel

        if not channel:
            return "global"

        normalized = str(channel).strip().lower()

        if normalized in VALID_CHANNELS:
            return normalized

        return "global"

    # ========================================================
    # Очередь провайдеров
    # ========================================================

    def _resolve_providers(self, channel: str) -> List[str]:
        providers = config.route(channel)

        if not providers:
            return ["google"]

        result: List[str] = []

        for provider_id in providers:
            if not isinstance(provider_id, str):
                continue

            provider_id = provider_id.strip().lower()

            if not provider_id:
                continue

            if provider_id not in result:
                result.append(provider_id)

        return result or ["google"]

    # ========================================================
    # Языки
    # ========================================================

    def _resolve_languages(
        self,
        providers: List[str],
        direction: str,
    ) -> tuple[Optional[str], Optional[str]]:
        if not providers:
            return None, None

        provider_id = providers[0]

        if direction == OUTGOING:
            return config.provider_outgoing_languages(provider_id)

        return config.provider_languages(provider_id)

    # ========================================================
    # Удобные публичные методы
    # ========================================================

    def route_for_context(self, context: MessageContext) -> List[str]:
        return self.resolve(context).providers

    def languages_for_context(
        self,
        context: MessageContext,
    ) -> tuple[Optional[str], Optional[str]]:
        decision = self.resolve(context)
        return decision.source_language, decision.target_language

    def is_outgoing(self, context: MessageContext) -> bool:
        return self._resolve_direction(context) == OUTGOING

    def is_incoming(self, context: MessageContext) -> bool:
        return self._resolve_direction(context) == INCOMING


# ============================================================
# Standalone test
# ============================================================

if __name__ == "__main__":
    from .models import ChatMessage

    router = TranslationRouter()

    tests = [
        ("Incoming Global", "global", None, "WTB mirror"),
        ("Incoming Local", "local", None, "Selling Mageblood"),
        ("Incoming Whisper", "whisper", None, "Hi, are you selling this?"),
        ("Outgoing To", "global", "To", "Куплю Mageblood"),
        ("Outgoing outgoing", "global", "outgoing", "Buy Mageblood"),
    ]

    for title, channel, direction, text in tests:
        message = ChatMessage(
            channel=channel,
            channel_symbol="#" if channel == "global" else "",
            sender="Tester",
            text=text,
            direction=direction,
        )

        decision = router.resolve(
            MessageContext.from_chat_message(message)
        )

        print(f"=== {title} ===")
        print("direction:", decision.direction)
        print("channel:", decision.channel)
        print("providers:", decision.providers)
        print(
            "languages:",
            decision.source_language,
            "->",
            decision.target_language,
        )
        print()
