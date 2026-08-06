import sys
import os
import json

from PyQt6.QtWidgets import QApplication

from core.log_reader import LogReaderThread
from core.log_parser import ChatMessage
from core.models import MessageContext
from core.translation_manager import TranslationManager

from ui.chat_overlay import ChatOverlay, GlobalHotkeyListener

from providers.google_translate import GoogleTranslateTranslator


# Стандартные пути к логам PoE (Standalone и Steam)
DEFAULT_LOG_PATHS = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\LatestClient.txt",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"D:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"E:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
]


def resolve_log_path() -> str:
    """Ищет путь к LatestClient.txt."""

    if os.path.exists("config.json"):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            custom_path = data.get("log_path")

            if custom_path and os.path.exists(custom_path):
                return custom_path

        except Exception as e:
            print(f"[Main] Ошибка чтения config.json: {e}")

    for path in DEFAULT_LOG_PATHS:
        if os.path.exists(path):
            return path

    return DEFAULT_LOG_PATHS[0]


class ExilingoApp:
    def __init__(self):

        self.app = QApplication(sys.argv)

        # ---------------------------------------------------
        # Overlay
        # ---------------------------------------------------

        self.overlay = ChatOverlay()

        # ---------------------------------------------------
        # Hotkey
        # ---------------------------------------------------

        self.hotkey_listener = GlobalHotkeyListener()
        self.hotkey_listener.toggle_requested.connect(self.overlay.toggle_mode)

        # ---------------------------------------------------
        # Translation Manager
        # ---------------------------------------------------

        self.translation_manager = TranslationManager(
            translator=GoogleTranslateTranslator(
                source_lang="en",
                target_lang="ru",
            )
        )

        self.translation_manager.translation_finished.connect(self.on_message_ready)

        self.translation_manager.start()

        # ---------------------------------------------------
        # Log Reader
        # ---------------------------------------------------

        log_path = resolve_log_path()

        print(f"[Main] Используется путь к логу: {log_path}")

        self.log_reader = LogReaderThread(
            log_filepath=log_path,
            read_from_end=True,
        )

        self.log_reader.new_chat_message.connect(self.on_new_chat_message)

        self.log_reader.status_changed.connect(self.on_log_status)

    # =======================================================
    # Log Reader
    # =======================================================

    def on_new_chat_message(self, msg: ChatMessage):

        context = MessageContext.from_chat_message(msg)

        self.translation_manager.enqueue(context)

    # =======================================================
    # Translation Pipeline
    # =======================================================

    def on_message_ready(self, context: MessageContext):

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

        self.overlay.add_message(
            channel_prefix=context.channel_symbol,
            sender=sender,
            text=context.display_text,
            is_translated=context.was_translated,
        )

    # =======================================================

    def on_log_status(self, status: str):
        print(f"[LogReader] {status}")

    # =======================================================

    def run(self):

        self.log_reader.start()

        self.overlay.show()

        self.overlay.add_message(
            "",
            "Exilingo",
            "Translation Pipeline готов.",
            is_translated=True,
        )

        ret = self.app.exec()

        self.log_reader.stop()
        self.translation_manager.stop()

        sys.exit(ret)


if __name__ == "__main__":
    app = ExilingoApp()
    app.run()
