from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


# ============================================================
# СЫРЫЕ ДАННЫЕ ИЗ ЛОГА
# ============================================================


@dataclass(slots=True)
class ChatMessage:
    """
    Сообщение игрового чата, полученное из LatestClient.txt.

    Это максимально близкое представление строки игрового чата.
    Объект никогда не изменяется после создания.
    """

    channel: str
    channel_symbol: str
    sender: str
    text: str

    guild_tag: Optional[str] = None
    direction: Optional[str] = None


@dataclass(slots=True)
class LogEntry:
    """
    Одна строка LatestClient.txt после разбора.
    """

    timestamp: datetime
    ticks: int
    hex_id: str

    level: str
    source: str
    pid: int

    category: Optional[str]
    message: str

    chat: Optional[ChatMessage] = None


# ============================================================
# РЕЗУЛЬТАТ РАБОТЫ ПЕРЕВОДЧИКА
# ============================================================


@dataclass(slots=True)
class TranslationResult:
    """
    Результат работы любого переводчика.

    Не зависит от конкретного API.
    Может быть получен от Google, Gemini, Groq,
    OpenRouter, DeepL, Ollama и т.д.
    """

    message: ChatMessage

    translated_text: str

    source_language: Optional[str] = None
    target_language: str = "ru"

    translator: str = "Unknown"

    success: bool = True
    from_cache: bool = False

    error: Optional[str] = None


# ============================================================
# ВНУТРЕННИЙ КОНТЕКСТ EXILINGO
# ============================================================


@dataclass(slots=True)
class MessageContext:
    """
    Главная рабочая модель Exilingo.

    Именно этот объект проходит через весь Pipeline.

    ChatMessage всегда остается неизменным,
    а MessageContext постепенно обогащается
    новыми данными.
    """

    # --------------------------------------------------------
    # Исходные данные
    # --------------------------------------------------------

    source: ChatMessage
    original_text: str

    # --------------------------------------------------------
    # Этапы Pipeline
    # --------------------------------------------------------

    normalized_text: Optional[str] = None

    translated_text: Optional[str] = None

    display_text: Optional[str] = None

    # --------------------------------------------------------
    # Информация о переводе
    # --------------------------------------------------------

    provider: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None

    from_cache: bool = False
    translation_success: bool = False

    error: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    # --------------------------------------------------------
    # Фабрика
    # --------------------------------------------------------

    @classmethod
    def from_chat_message(cls, message: ChatMessage) -> "MessageContext":
        """
        Создает MessageContext из ChatMessage.

        Это основной способ создания объекта,
        используемый Translation Pipeline.
        """

        return cls(
            source=message,
            original_text=message.text,
        )

    # --------------------------------------------------------
    # Удобные свойства
    # --------------------------------------------------------

    @property
    def sender(self) -> str:
        return self.source.sender

    @property
    def channel(self) -> str:
        return self.source.channel

    @property
    def channel_symbol(self) -> str:
        return self.source.channel_symbol

    @property
    def guild_tag(self) -> Optional[str]:
        return self.source.guild_tag

    @property
    def direction(self) -> Optional[str]:
        return self.source.direction

    @property
    def original_message(self) -> ChatMessage:
        """
        Возвращает исходный ChatMessage.
        """
        return self.source

    @property
    def was_translated(self) -> bool:
        """
        Используется Overlay.

        True — если сообщение было успешно переведено.
        False — если отображается оригинальный текст.
        """
        return self.translation_success and bool(self.display_text)
