import sys
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.logger import (
    get_logger,
    log_exception,
    log_settings_snapshot,
    setup_logging,
    shutdown_logging,
)

from core.log_reader import LogReaderThread
from core.log_parser import ChatMessage
from core.models import MessageContext
from core.translation_manager import TranslationManager
from core.translation_router import TranslationRouter
from core.config_manager import config
from core.provider_registry import ProviderRegistry
from core.game_chat_sender import GameChatSender

from ui.chat_overlay import ChatOverlay, GlobalHotkeyListener
from ui.settings_dialog import SettingsDialog


# Стандартные пути к логам PoE (Standalone и Steam)
DEFAULT_LOG_PATHS = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\LatestClient.txt",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"D:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"E:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
]


# ============================================================
# Игровые каналы исходящих сообщений
# ============================================================

OUTGOING_CHANNELS = {
    "": ("local", ""),
    "#": ("global", "#"),
    "%": ("party", "%"),
    "@": ("whisper", "@"),
    "$": ("trade", "$"),
    "&": ("guild", "&"),
}


# ============================================================
# F5 — отправка сообщения без переключения режима Overlay
# ============================================================


class OutgoingHotkeyListener(QObject):
    """
    Отдельный глобальный слушатель F5.

    Enter остаётся полностью за GlobalHotkeyListener и
    переключает режим Overlay.

    F5 только инициирует отправку текущего текста из Overlay
    и никогда не меняет режим click-through.
    """

    send_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self._keyboard = None
        self.logger = get_logger("Hotkey")

        try:
            import keyboard

            self._keyboard = keyboard

            keyboard.add_hotkey(
                "f5",
                self._on_f5,
            )

            self.logger.info("F5 registered for outgoing message sending.")

        except Exception as e:
            self.logger.error(
                "Failed to register F5: %s",
                e,
                exc_info=True,
            )

    def _on_f5(self):
        self.logger.debug("F5 pressed -> send request.")
        self.send_requested.emit()

    def stop(self):
        if self._keyboard is None:
            return

        try:
            self._keyboard.remove_hotkey("f5")
            self.logger.debug("F5 unregistered.")
        except Exception as e:
            self.logger.error(
                "Failed to unregister F5: %s",
                e,
                exc_info=True,
            )


class ExilingoApp:
    def __init__(self):

        self.logger = get_logger("Main")

        self.app = QApplication(sys.argv)

        self.logger.info("Exilingo application initialized.")

        # ---------------------------------------------------
        # Overlay
        # ---------------------------------------------------

        self.overlay = ChatOverlay()

        self.overlay.close_requested.connect(self.close_application)

        self.overlay.settings_requested.connect(self.open_settings)

        # Исходящие сообщения из поля ввода Overlay.
        self.overlay.send_message_requested.connect(self.on_outgoing_message)

        # ---------------------------------------------------
        # Hotkey
        # ---------------------------------------------------

        self.hotkey_listener = GlobalHotkeyListener()

        # Enter = только переключение режима Overlay.
        self.hotkey_listener.toggle_requested.connect(self.overlay.toggle_mode)

        # F5 = только отправка текущего сообщения.
        # Режим Overlay при этом НЕ меняется.
        self.outgoing_hotkey_listener = OutgoingHotkeyListener()

        self.outgoing_hotkey_listener.send_requested.connect(self.overlay._on_send)

        # ---------------------------------------------------
        # Provider Registry + Router
        # ---------------------------------------------------

        self.provider_registry = ProviderRegistry()
        self.translation_router = TranslationRouter()

        # ---------------------------------------------------
        # Translation Manager
        # ---------------------------------------------------

        self.translation_manager = TranslationManager(
            registry=self.provider_registry,
            router=self.translation_router,
        )

        self.translation_manager.translation_finished.connect(self.on_message_ready)

        self.translation_manager.translation_failed.connect(self.on_translation_failed)

        self.translation_manager.start()

        # ---------------------------------------------------
        # Game Chat Sender
        # ---------------------------------------------------

        self.game_chat_sender = GameChatSender()

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

        self.logger.info(
            "Using Path of Exile log path: %s",
            log_path,
        )

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
        """Завершает работу программы."""

        self.logger.info("Application shutdown requested.")

        try:
            self.outgoing_hotkey_listener.stop()
        except Exception:
            self.logger.exception("Error while stopping outgoing hotkey listener.")

        self.app.quit()

    # -------------------------------------------------------

    def open_settings(self):
        """Открывает полноценное окно настроек Exilingo."""

        self.logger.info("Settings window opened.")

        try:
            accepted = SettingsDialog.open_settings(
                self.overlay,
            )

            if accepted:
                self.logger.info("Settings saved.")
            else:
                self.logger.info("Settings cancelled.")

        except Exception:
            self.logger.exception("Unhandled exception while opening settings.")

    # =======================================================
    # Log Reader
    # =======================================================

    def on_new_chat_message(
        self,
        msg: ChatMessage,
    ):

        self.logger.info(
            "Incoming chat message: channel=%r sender=%r text=%r",
            msg.channel,
            msg.sender,
            msg.text,
        )

        context = MessageContext.from_chat_message(msg)

        self.translation_manager.enqueue(context)

    # =======================================================
    # Outgoing Overlay -> TranslationManager
    # =======================================================

    def on_outgoing_message(
        self,
        text: str,
    ):
        """
        Получает сообщение из поля ввода Overlay.

        Overlay уже добавляет игровой prefix, если пользователь
        не указал его самостоятельно.
        """

        text = str(text or "").strip()

        if not text:
            self.logger.debug("Empty outgoing message ignored.")
            return

        prefix = text[0] if text[0] in OUTGOING_CHANNELS else ""

        channel, channel_symbol = OUTGOING_CHANNELS.get(
            prefix,
            ("local", ""),
        )

        msg = ChatMessage(
            channel=channel,
            channel_symbol=channel_symbol,
            sender="You",
            text=text,
            direction="outgoing",
        )

        self.logger.info(
            "Outgoing message from Overlay: text=%r channel=%s prefix=%r",
            text,
            channel,
            prefix,
        )

        self.translation_manager.enqueue(MessageContext.from_chat_message(msg))

    # =======================================================
    # Translation Pipeline
    # =======================================================

    def on_message_ready(
        self,
        context: MessageContext,
    ):
        """
        Incoming:
            сообщение отображается в Overlay.

        Outgoing:
            перевод отправляется в игровой чат через
            GameChatSender.

        Outgoing НЕ отображается напрямую в Overlay.
        После отправки PoE должна записать сообщение в
        LatestClient.txt, после чего оно вернётся через
        обычный LogReader -> LogParser -> TranslationManager.
        """

        self.logger.info(
            "Translation completed: text=%r provider=%r direction=%r",
            context.display_text,
            context.provider,
            context.direction,
        )

        is_outgoing = context.direction is not None and str(
            context.direction
        ).strip().lower() in {
            "outgoing",
            "out",
            "send",
            "sent",
            "to",
            "кому",
        }

        # ---------------------------------------------------
        # Outgoing
        # ---------------------------------------------------

        if is_outgoing:
            prepared_text = context.display_text or context.original_text
            is_local = str(context.channel or "").strip().lower() == "local"

            self.logger.info(
                "OUTGOING -> GameChatSender.send(): %r local=%s",
                prepared_text,
                is_local,
            )

            sent = self.game_chat_sender.send(
                prepared_text,
                local=is_local,
            )

            if not sent:
                self.logger.error("OUTGOING FAILED: GameChatSender returned False.")
            else:
                self.logger.info("OUTGOING OK: message passed to GameChatSender.")

            # Никогда не рисуем outgoing напрямую.
            return

        # ---------------------------------------------------
        # Incoming
        # ---------------------------------------------------

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

        self.logger.info(
            "INCOMING -> Overlay.add_message(): sender=%r text=%r",
            sender,
            context.display_text,
        )

        self.overlay.add_message(
            channel_prefix=context.channel_symbol,
            sender=sender,
            text=context.display_text,
            is_translated=context.translation_success,
        )

    # -------------------------------------------------------

    def on_translation_failed(
        self,
        context: MessageContext,
        error: str,
    ):
        """Обрабатывает ситуацию, когда все провайдеры перевода завершились ошибкой."""

        self.logger.error(
            "Translation failed: original=%r error=%r direction=%r",
            context.original_text,
            error,
            context.direction,
        )

        is_outgoing = context.direction is not None and str(
            context.direction
        ).strip().lower() in {
            "outgoing",
            "out",
            "send",
            "sent",
            "to",
            "кому",
        }

        if is_outgoing:
            is_local = str(context.channel or "").strip().lower() == "local"

            self.logger.warning(
                "OUTGOING FALLBACK -> GameChatSender.send(): %r local=%s",
                context.original_text,
                is_local,
            )

            sent = self.game_chat_sender.send(
                context.original_text,
                local=is_local,
            )

            if not sent:
                self.logger.error("OUTGOING FALLBACK FAILED.")
            else:
                self.logger.info("OUTGOING FALLBACK OK.")

            # Не рисуем outgoing напрямую.
            return

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

        self.overlay.add_message(
            channel_prefix=context.channel_symbol,
            sender=sender,
            text=context.original_text,
            is_translated=False,
        )

    # =======================================================

    def on_log_status(
        self,
        status: str,
    ):

        self.logger.info(
            "LogReader: %s",
            status,
        )

    # =======================================================

    def run(self):

        self.log_reader.start()

        self.logger.info("LogReader monitoring started.")

        self.overlay.show()

        self.overlay.add_message(
            "",
            "Exilingo",
            "Translation Pipeline готов.",
            is_translated=True,
        )

        ret = self.app.exec()

        self.logger.info(
            "Qt event loop finished with exit code %s.",
            ret,
        )

        self.log_reader.stop()
        self.translation_manager.stop()

        try:
            self.outgoing_hotkey_listener.stop()
        except Exception:
            self.logger.exception("Error while stopping outgoing hotkey listener.")

        sys.exit(ret)


if __name__ == "__main__":
    # Логирование и снимок настроек создаются до запуска основного приложения.
    logger = setup_logging()

    try:
        log_settings_snapshot(
            config.data,
            logger=get_logger("Settings"),
        )

        app = ExilingoApp()
        app.run()

    except SystemExit:
        raise

    except Exception:
        log_exception(
            logger,
            "Unhandled exception at application top level.",
        )
        raise

    finally:
        shutdown_logging()
