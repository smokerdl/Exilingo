from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(slots=True)
class ChatMessage:
    """
    Сообщение игрового чата, полученное из LatestClient.txt.
    Это "сырая" модель данных, максимально близкая к тому,
    что записывает клиент Path of Exile.
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


@dataclass(slots=True)
class MessageContext:
    """
    Внутренняя модель Exilingo.

    Именно этот объект будет проходить через Message Pipeline.
    Все этапы обработки работают ТОЛЬКО с ним.

    ChatMessage никогда не изменяется.
    """

    source: ChatMessage

    # Исходный текст
    original_text: str

    # После словаря
    normalized_text: Optional[str] = None

    # После перевода
    translated_text: Optional[str] = None

    # Итоговый текст, который увидит пользователь
    display_text: Optional[str] = None

    # Информация о переводе
    provider: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None

    # Служебная информация
    metadata: Dict[str, Any] = field(default_factory=dict)

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