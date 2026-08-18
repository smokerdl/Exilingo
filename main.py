import sys

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

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
from core.game_window import GameWindowController

from ui.chat_overlay import ChatOverlay, GlobalHotkeyListener
from ui.settings_dialog import SettingsDialog


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
        """Безопасно снимает F5; повторный вызов ничего не делает."""
        keyboard_module = self._keyboard

        if keyboard_module is None:
            return

        try:
            keyboard_module.remove_hotkey("f5")
            self.logger.debug("F5 unregistered.")
        except KeyError:
            self.logger.debug("F5 was already unregistered.")
        except Exception as e:
            self.logger.error(
                "Failed to unregister F5: %s",
                e,
                exc_info=True,
            )
        finally:
            self._keyboard = None


class ExilingoApp:
    def __init__(self):

        self.logger = get_logger("Main")

        self.app = QApplication(sys.argv)

        # Application-level Quit/Close should be explicit. The system tray
        # keeps the process alive while the Overlay itself is hidden.
        self.app.setQuitOnLastWindowClosed(False)

        self.logger.info("Exilingo application initialized.")

        # ---------------------------------------------------
        # Overlay + PoE window controller
        # ---------------------------------------------------

        self.overlay = ChatOverlay()
        self.game_window_controller = GameWindowController()

        self.overlay.close_requested.connect(self.close_application)
        self.overlay.settings_requested.connect(self.open_settings)
        self.overlay.send_message_requested.connect(self.on_outgoing_message)

        # ---------------------------------------------------
        # System tray
        # ---------------------------------------------------

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(
            self.app.style().standardIcon(
                self.app.style().StandardPixmap.SP_ComputerIcon
            )
        )
        self.tray_icon.setToolTip("Exilingo")

        tray_menu = QMenu()

        show_action = QAction("Показать Exilingo", self)
        show_action.triggered.connect(self._show_overlay_from_tray)
        tray_menu.addAction(show_action)

        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)

        tray_menu.addSeparator()

        quit_action = QAction("Выйти", self)
        quit_action.triggered.connect(self.close_application)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        # ---------------------------------------------------
        # Hotkey
        # ---------------------------------------------------

        self.hotkey_listener = GlobalHotkeyListener()
        self.hotkey_listener.toggle_requested.connect(self.overlay.toggle_mode)

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
            self.logger.warning(
                "Path of Exile log path is not configured. Opening settings for first-time setup."
            )

            if not self._open_settings_dialog():
                raise RuntimeError(
                    "Path of Exile log path is not configured. "
                    "Configure general.log_path in Settings."
                )

            log_path = config.log_path

        if not log_path:
            raise RuntimeError(
                "Path of Exile log path is not configured. "
                "Configure general.log_path in Settings."
            )

        self.logger.info(
            "Using Path of Exile log path: %s",
            log_path,
        )

        self.log_reader = LogReaderThread(
            log_filepath=log_path,
            read_from_end=True,
        )

        self.log_reader.new_chat_message.connect(self.on_new_chat_message)
        self.log_reader.window_focus_changed.connect(self.on_game_focus_changed)
        self.log_reader.status_changed.connect(self.on_log_status)

    # =======================================================
    # System tray
    # =======================================================

    def _show_overlay_from_tray(self):
        """Показывает Overlay и возвращает его в обычное состояние."""
        self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()

    def _on_tray_activated(self, reason):
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            if self.overlay.isVisible():
                self.overlay.hide()
            else:
                self._show_overlay_from_tray()

    # =======================================================
    # Верхняя панель Overlay
    # =======================================================

    def close_application(self):
        """Полностью завершает работу программы."""

        self.logger.info("Application shutdown requested.")

        try:
            self.outgoing_hotkey_listener.stop()
        except Exception:
            self.logger.exception("Error while stopping outgoing hotkey listener.")

        try:
            self.tray_icon.hide()
        except Exception:
            self.logger.exception("Error while hiding system tray icon.")

        self.app.quit()

    def _apply_runtime_settings(self):
        """Применяет изменённые настройки Overlay к уже запущенному окну."""

        geometry = config.overlay_geometry or {}

        try:
            self.overlay.setGeometry(
                int(geometry.get("x", self.overlay.x())),
                int(geometry.get("y", self.overlay.y())),
                int(geometry.get("w", self.overlay.width())),
                int(geometry.get("h", self.overlay.height())),
            )
        except (TypeError, ValueError):
            self.logger.warning(
                "Invalid overlay geometry in config; keeping current geometry."
            )

        try:
            self.overlay.set_font_size(int(config.font_size))
        except (TypeError, ValueError):
            self.logger.warning(
                "Invalid overlay font size in config; keeping current font size."
            )

    def _open_settings_dialog(self):
        """Открывает окно настроек без системной шапки и возвращает результат."""

        self.logger.info("Settings window opened.")

        try:
            dialog = SettingsDialog(self.overlay)

            dialog.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )

            accepted = dialog.exec() == dialog.DialogCode.Accepted

            if accepted:
                self._apply_runtime_settings()
                self.logger.info("Settings saved.")
            else:
                self.logger.info("Settings cancelled.")

            return accepted

        except Exception:
            self.logger.exception("Unhandled exception while opening settings.")
            return False

    def open_settings(self):
        """Открывает полноценное окно настроек Exilingo без системной шапки."""
        self._open_settings_dialog()

    # =======================================================
    # Log Reader
    # =======================================================

    def on_new_chat_message(self, msg: ChatMessage):

        self.logger.info(
            "Incoming chat message: channel=%r sender=%r text=%r",
            msg.channel,
            msg.sender,
            msg.text,
        )

        context = MessageContext.from_chat_message(msg)
        self.translation_manager.enqueue(context)

    def on_game_focus_changed(self, focused: bool):
        """Синхронизирует видимость Overlay с состоянием окна PoE."""

        self.logger.info(
            "PoE window focus event: %s",
            "Gained focus" if focused else "Lost focus",
        )

        minimized = self.game_window_controller.is_minimized()

        if minimized is True:
            self.logger.info("PoE is minimized -> hiding Exilingo Overlay to system tray.")
            self.overlay.hide()
            return

        if minimized is False:
            self.logger.info("PoE is not minimized -> showing Exilingo Overlay.")
            self._show_overlay_from_tray()
            return

        self.logger.warning(
            "PoE window could not be located; keeping current Exilingo Overlay state."
        )

    def _sync_overlay_with_game_window(self):
        """Синхронизирует Overlay с PoE при запуске Exilingo."""

        minimized = self.game_window_controller.is_minimized()

        if minimized is True:
            self.logger.info("PoE is already minimized at startup -> hiding Overlay to system tray.")
            self.overlay.hide()
        elif minimized is False:
            self.logger.info("PoE is not minimized at startup -> showing Overlay.")
            self.overlay.show()
        else:
            self.logger.info("PoE window not found at startup -> showing Overlay.")
            self.overlay.show()

    # =======================================================
    # Outgoing Overlay -> TranslationManager
    # =======================================================

    def on_outgoing_message(self, text: str):
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

    def on_message_ready(self, context: MessageContext):
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

        is_outgoing = context.direction is not None and str(context.direction).strip().lower() in {
            "outgoing",
            "out",
            "send",
            "sent",
            "to",
            "кому",
        }

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

            return

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

    def on_translation_failed(self, context: MessageContext, error: str):
        """Обрабатывает ситуацию, когда все провайдеры перевода завершились ошибкой."""

        self.logger.error(
            "Translation failed: original=%r error=%r direction=%r",
            context.original_text,
            error,
            context.direction,
        )

        is_outgoing = context.direction is not None and str(context.direction).strip().lower() in {
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

    def on_log_status(self, status: str):

        self.logger.info(
            "LogReader: %s",
            status,
        )

    # =======================================================

    def run(self):

        self.log_reader.start()

        self.logger.info("LogReader monitoring started.")

        self._sync_overlay_with_game_window()

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
