import re
from datetime import datetime
from typing import Dict, Generator, Optional

from .models import ChatMessage, LogEntry

# Маппинг префиксов на понятные названия каналов
CHANNEL_MAP: Dict[Optional[str], str] = {
    "#": "global",
    "%": "party",
    "@": "whisper",
    "$": "trade",
    "&": "guild",
    "": "local"  # Локальный чат области (без символа)
}


class PoELogParser:
    """Парсер логов клиента Path of Exile (LatestClient.txt)."""

    # Регулярка для базовой структуры строки
    LOG_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\s+"
        r"(?P<ticks>\d+)\s+"
        r"(?P<hex_id>[0-9a-fA-F]+)\s+"
        r"\[(?P<level>\w+)\s+(?P<source>\w+)\s+(?P<pid>\d+)\]\s+"
        r"(?:\[(?P<category>[^\]]+)\]\s+)?"
        r"(?P<message>.*)$"
    )

    # Регулярка для фильтрации сообщений чата игроков
    CHAT_PATTERN = re.compile(
        r"^(?P<prefix>[#%$&@])?"
        r"(?:(?P<direction>From|To|От кого|Кому)\s+)?"
        r"(?:<(?P<guild_tag>[^>]+)>\s*)?"
        r"(?P<sender>[^:]+):\s+"
        r"(?P<text>.*)$"
    )

    def parse_line(self, raw_line: str) -> Optional[LogEntry]:
        """Парсит одну строку из файла логов."""
        raw_line = raw_line.strip()
        if not raw_line:
            return None

        match = self.LOG_PATTERN.match(raw_line)
        if not match:
            return None

        data = match.groupdict()

        # Время
        dt = datetime.strptime(data["timestamp"], "%Y/%m/%d %H:%M:%S")

        category = data.get("category")
        message = data["message"]

        # Извлечение чата (если строка является сообщением)
        chat_data = self.parse_chat(message, category)

        return LogEntry(
            timestamp=dt,
            ticks=int(data["ticks"]),
            hex_id=data["hex_id"],
            level=data["level"],
            source=data["source"],
            pid=int(data["pid"]),
            category=category,
            message=message,
            chat=chat_data,
        )

    def parse_chat(
        self,
        message: str,
        category: Optional[str] = None,
    ) -> Optional[ChatMessage]:
        """Выделяет чат пользователя из текста сообщения."""

        # У сообщений чата пользователей не бывает категорий
        # вида [WINDOW], [HTTP2] и т.д.
        if category is not None:
            return None

        # Отсекаем системные оповещения
        if message.startswith(":") or message.startswith("&:"):
            return None

        match = self.CHAT_PATTERN.match(message)
        if not match:
            return None

        data = match.groupdict()
        prefix = data.get("prefix") or ""

        return ChatMessage(
            channel=CHANNEL_MAP.get(prefix, "local"),
            channel_symbol=prefix,
            sender=data["sender"].strip(),
            text=data["text"].strip(),
            guild_tag=data.get("guild_tag"),
            direction=data.get("direction"),
        )

    def read_file(
        self,
        filepath: str,
        encoding: str = "utf-8",
    ) -> Generator[LogEntry, None, None]:
        """Генератор для чтения и парсинга всего файла по строкам."""

        with open(filepath, "r", encoding=encoding, errors="replace") as f:
            for line in f:
                entry = self.parse_line(line)
                if entry:
                    yield entry


# Пример использования при прямом запуске скрипта
if __name__ == "__main__":
    parser = PoELogParser()

    sample_lines = [
        "2026/08/04 19:46:25 35949437 f95436cc [INFO Client 22852] [HTTP2] User agent: PoE release",
        "2026/08/04 19:46:40 35963781 cffb065b [INFO Client 22852] : <<set:MP>>Вы вошли в область Берега Каруи.",
        "2026/08/04 19:48:00 36044031 cffb065b [INFO Client 22852] #<YMCMB> InFlameZ: any bosskillers aroujnd?",
        "2026/08/04 19:49:32 36135765 cffb065b [INFO Client 22852] <GRINED> Lebowski_Allflame: поп",
        "2026/08/04 19:50:23 36187546 cffb065b [INFO Client 22852] #FlameYes: i inflated yo mama",
        "2026/08/04 19:51:39 36263093 f9532a4e [INFO Client 22852] Closing game gracefully",
    ]

    print("--- Результат парсинга точечно чата ---")

    for line in sample_lines:
        entry = parser.parse_line(line)

        if entry and entry.chat:
            c = entry.chat
            tag = f"[{c.guild_tag}] " if c.guild_tag else ""
            print(
                f"[{entry.timestamp.strftime('%H:%M:%S')}] "
                f"[{c.channel.upper()}] {tag}{c.sender}: {c.text}"
            )