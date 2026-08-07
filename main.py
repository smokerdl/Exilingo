import sys
import os

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.log_reader import LogReaderThread
from core.log_parser import ChatMessage
from core.models import MessageContext
from core.translation_manager import TranslationManager
from core.config_manager import config
from core.provider_registry import ProviderRegistry

from ui.chat_overlay import ChatOverlay, GlobalHotkeyListener


# Стандартные пути к логам PoE (Standalone и Steam)
DEFAULT_LOG_PATHS = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\LatestClient.txt",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"D:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"E:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
]


class ExilingoApp:
    def __init__(self):

        self.app = QApplication(sys.argv)

        # ---------------------------------------------------
        # Overlay
        # ---------------------------------------------------

        self.overlay = ChatOverlay()

        # Кнопки верхней панели
        self.overlay.close_requested.connect(self.close_application)
        self.overlay.settings_requested.connect(self.open_settings)

        # ---------------------------------------------------
        # Hotkey
        # ---------------------------------------------------

        self.hotkey_listener = GlobalHotkeyListener()
        self.hotkey_listener.toggle_requested.connect(self.overlay.toggle_mode)

        # ---------------------------------------------------
        # Translation Manager
        # ---------------------------------------------------

        registry = ProviderRegistry()
        translator = registry.create(config.provider)

        self.translation_manager = TranslationManager(
            translator=translator,
        )

        self.translation_manager.translation_finished.connect(self.on_message_ready)

        self.translation_manager.start()

        # ---------------------------------------------------
        # Log Reader
        # ---------------------------------------------------

        log_path = config.log_path

        if not log_path:
            for path in DEFAULT_LOG_PATHS:
                if os.path.exists(path):
                    log_path = path
                    break

            if not log_path:
                log_path = DEFAULT_LOG_PATHS[0]

            config.log_path = log_path

        print(f"[Main] Используется путь к логу: {log_path}")

        self.log_reader = LogReaderThread(
            log_filepath=log_path,
            read_from_end=True,
        )

        self.log_reader.new_chat_message.connect(self.on_new_chat_message)

        self.log_reader.status_changed.connect(self.on_log_status)

    # =======================================================
    # Верхняя панель Overlay
    # =======================================================

    def close_application(self):
        """
        Завершает работу программы.
        """

        print("[MAIN] Завершение работы...")

        self.app.quit()

    # -------------------------------------------------------

    def open_settings(self):
        """
        Пока окно настроек не реализовано.
        """

        print("[MAIN] Открытие окна настроек")

        QMessageBox.information(
            self.overlay,
            "Настройки",
            "Окно настроек пока находится в разработке.",
        )

    # =======================================================
    # Log Reader
    # =======================================================

    def on_new_chat_message(self, msg: ChatMessage):

        print("[MAIN] Получено сообщение:", msg.text)

        context = MessageContext.from_chat_message(msg)

        self.translation_manager.enqueue(context)

    # =======================================================
    # Translation Pipeline
    # =======================================================

    def on_message_ready(self, context: MessageContext):

        print("[MAIN] Отправляем в Overlay:", context.display_text)

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

        self.overlay.add_message(
            channel_prefix=context.channel_symbol,
            sender=sender,
            text=context.display_text,
            is_translated=context.translation_success,
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
