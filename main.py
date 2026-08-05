import sys
import os
import json
from PyQt6.QtWidgets import QApplication

from core.log_reader import LogReaderThread
from core.log_parser import ChatMessage
from ui.chat_overlay import ChatOverlay, GlobalHotkeyListener

# Стандартные пути к логам PoE (Standalone и Steam)
DEFAULT_LOG_PATHS = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\LatestClient.txt",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"D:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"E:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
]


def resolve_log_path() -> str:
    """Ищет путь к LatestClient.txt из config.json или проверяет стандартные места."""
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                custom_path = data.get("log_path")
                if custom_path and os.path.exists(custom_path):
                    return custom_path
        except Exception as e:
            print(f"[Main] Ошибка чтения config.json: {e}")

    # Проверяем список популярных путей
    for path in DEFAULT_LOG_PATHS:
        if os.path.exists(path):
            return path

    # Возвращаем дефолтный путь по умолчанию, даже если он ещё не создан
    return DEFAULT_LOG_PATHS[0]


class ExilingoApp:
    def __init__(self):
        self.app = QApplication(sys.argv)

        # 1. Создаем интерфейс оверлея
        self.overlay = ChatOverlay()

        # 2. Регистрируем глобальный хоткей на Enter
        self.hotkey_listener = GlobalHotkeyListener()
        self.hotkey_listener.toggle_requested.connect(self.overlay.toggle_mode)

        # 3. Определяем путь к логам и запускаем фоновый читатель
        log_path = resolve_log_path()
        print(f"[Main] Используется путь к логу: {log_path}")

        # read_from_end=True читает только НОВЫЕ сообщения после запуска программы
        self.log_reader = LogReaderThread(log_filepath=log_path, read_from_end=True)
        self.log_reader.new_chat_message.connect(self.on_new_chat_message)
        self.log_reader.status_changed.connect(self.on_log_status)

    def on_new_chat_message(self, msg: ChatMessage):
        """Слот обработки нового сообщения из логов игры."""
        # Собираем красивое имя отправителя (с гильдией, если она есть)
        sender_display = f"<{msg.guild_tag}> {msg.sender}" if msg.guild_tag else msg.sender

        # Отправляем в окно чата
        # (is_translated=False пока выводит текст 'как есть', позже подключим переводчик)
        self.overlay.add_message(
            channel_prefix=msg.channel_symbol,
            sender=sender_display,
            text=msg.text,
            is_translated=False
        )

    def on_log_status(self, status: str):
        print(f"[LogReader Status] {status}")

    def run(self):
        # Запускаем поток логов и показываем окно
        self.log_reader.start()
        self.overlay.show()

        # Приветственное сообщение в чат
        self.overlay.add_message("", "Exilingo", "Приложение запущено и отслеживает чат!", is_translated=True)

        ret = self.app.exec()

        # При закрытии программы останавливаем фоновый поток
        self.log_reader.stop()
        sys.exit(ret)


if __name__ == "__main__":
    app = ExilingoApp()
    app.run()