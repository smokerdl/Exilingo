import sys

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

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
from core.hotkey_manager import HotkeyManager
from core.overlay_state import OverlayStateController

from ui.chat_overlay import ChatOverlay
from ui.settings_dialog import SettingsDialog
from ui._interaction_patch import set_mode_change_callback
from ui._settings_runtime_patch import set_runtime_callbacks


OUTGOING_CHANNELS = {
    "": ("local", ""),
    "#": ("global", "#"),
    "%": ("party", "%"),
    "@": ("whisper", "@"),
    "$": ("trade", "$"),
    "&": ("guild", "&"),
}


class _HotkeySignals(QObject):
    """Marshals global keyboard callbacks onto Qt's main thread.

    The `keyboard` package invokes callbacks from its own listener thread.
    Those callbacks must never manipulate Qt widgets directly. Emitting a
    signal from that thread and connecting it to a QObject living in the main
    thread makes Qt queue the actual UI operation safely.
    """

    send_message = pyqtSignal()
    toggle_mode = pyqtSignal()
    toggle_visibility = pyqtSignal()


class ExilingoApp:
    def __init__(self):
        self.logger = get_logger("Main")

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.logger.info("Exilingo application initialized.")

        self.overlay = ChatOverlay()
        self.game_window_controller = GameWindowController()
        self.overlay_state = OverlayStateController(self)
        set_mode_change_callback(self.overlay_state.on_overlay_mode_changed)

        self.overlay.close_requested.connect(self.close_application)
        self.overlay.settings_requested.connect(self.open_settings)
        self.overlay.send_message_requested.connect(self.on_outgoing_message)

        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setIcon(
            self.app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        self.tray_icon.setToolTip("Exilingo")

        tray_menu = QMenu()
        show_action = QAction("Показать Exilingo", self.app)
        show_action.triggered.connect(self._show_overlay_from_tray)
        tray_menu.addAction(show_action)

        settings_action = QAction("Настройки", self.app)
        settings_action.triggered.connect(self.open_settings)
        tray_menu.addAction(settings_action)
        tray_menu.addSeparator()

        quit_action = QAction("Выйти", self.app)
        quit_action.triggered.connect(self.close_application)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

        self.provider_registry = ProviderRegistry()
        self.translation_router = TranslationRouter()
        self.translation_manager = TranslationManager(
            registry=self.provider_registry,
            router=self.translation_router,
        )
        self.translation_manager.translation_finished.connect(self.on_message_ready)
        self.translation_manager.translation_failed.connect(self.on_translation_failed)
        self.translation_manager.start()

        self.game_chat_sender = GameChatSender()

        # `keyboard` invokes its callbacks outside Qt's GUI thread. Never pass
        # QWidget methods or other UI/state-changing callbacks directly to it.
        # The signal object belongs to this main-thread application and Qt will
        # queue these signal deliveries back to the GUI thread.
        self.hotkey_signals = _HotkeySignals()
        self.hotkey_signals.send_message.connect(self.overlay._on_send)
        self.hotkey_signals.toggle_mode.connect(self.on_toggle_overlay_mode)
        self.hotkey_signals.toggle_visibility.connect(self.on_toggle_overlay_visibility)

        self.hotkey_manager = HotkeyManager(
            {
                "send_message": self.hotkey_signals.send_message.emit,
                "toggle_mode": self.hotkey_signals.toggle_mode.emit,
                "toggle_visibility": self.hotkey_signals.toggle_visibility.emit,
            }
        )
        set_runtime_callbacks(self._apply_runtime_settings, self.hotkey_manager.reload)

        log_path = config.log_path
        if not log_path:
            self.logger.warning(
                "Path of Exile log path is not configured. Opening settings for first-time setup."
            )
            if not self._open_settings_dialog():
                raise RuntimeError(
                    "Path of Exile log path is not configured. Configure general.log_path in Settings."
                )
            log_path = config.log_path

        if not log_path:
            raise RuntimeError(
                "Path of Exile log path is not configured. Configure general.log_path in Settings."
            )

        self.logger.info("Using Path of Exile log path: %s", log_path)
        self.log_reader = LogReaderThread(
            log_filepath=log_path,
            read_from_end=True,
        )
        self.log_reader.new_chat_message.connect(self.on_new_chat_message)
        self.log_reader.window_focus_changed.connect(self.on_game_focus_changed)
        self.log_reader.status_changed.connect(self.on_log_status)

    # =======================================================
    # System tray / visibility
    # =======================================================

    def _show_overlay_from_tray(self):
        self.overlay_state.manual_show()

    def _on_tray_activated(self, reason):
        if reason not in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            return

        if self.overlay.isVisible():
            self.overlay_state.manual_hide()
        else:
            self.overlay_state.manual_show()

    def on_toggle_overlay_visibility(self):
        self.logger.info("Overlay visibility hotkey pressed.")
        self.overlay_state.toggle_user_visibility()

    # =======================================================
    # Shutdown / settings
    # =======================================================

    def close_application(self):
        self.logger.info("Application shutdown requested.")
        try:
            self.hotkey_manager.stop()
        except Exception:
            self.logger.exception("Error while stopping configured hotkeys.")
        try:
            self.tray_icon.hide()
        except Exception:
            self.logger.exception("Error while hiding system tray icon.")
        self.app.quit()

    def _apply_runtime_settings(self):
        geometry = config.overlay_geometry or {}
        try:
            self.overlay.setGeometry(
                int(geometry.get("x", self.overlay.x())),
                int(geometry.get("y", self.overlay.y())),
                int(geometry.get("w", self.overlay.width())),
                int(geometry.get("h", self.overlay.height())),
            )
        except (TypeError, ValueError):
            self.logger.warning("Invalid overlay geometry in config; keeping current geometry.")

        try:
            self.overlay.set_font_size(int(config.font_size))
        except (TypeError, ValueError):
            self.logger.warning("Invalid overlay font size in config; keeping current font size.")

    def _open_settings_dialog(self):
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
        self._open_settings_dialog()

    # =======================================================
    # Overlay / PoE state
    # =======================================================

    def on_toggle_overlay_mode(self):
        target = not self.overlay_state.desired_input_mode
        self.logger.info("Overlay mode hotkey -> desired interactive=%r", target)
        self.overlay_state.set_desired_input_mode(target)

    def on_game_focus_changed(self, focused: bool):
        self.logger.info(
            "PoE window focus event: %s",
            "Gained focus" if focused else "Lost focus",
        )

        if self.overlay.is_input_mode:
            self.logger.debug("Interactive mode active -> ignoring PoE focus event.")
            return

        self.overlay_state.on_game_focus_changed(bool(focused))

        if focused:
            self.logger.info("PoE gained focus in click-through mode -> syncing Overlay.")
        else:
            self.logger.info("PoE lost focus in click-through mode -> syncing Overlay.")

    def _sync_overlay_with_game_window(self):
        foreground = self.game_window_controller.is_foreground()
        if foreground is None:
            self.logger.info("PoE window not found at startup -> showing Overlay.")
            foreground = True

        self.overlay_state.desired_input_mode = bool(self.overlay.is_input_mode)
        self.overlay_state.set_initial_game_state(foreground)

    # =======================================================
    # Chat / translation pipeline
    # =======================================================

    def on_new_chat_message(self, msg: ChatMessage):
        self.logger.info(
            "Incoming chat message: channel=%r sender=%r text=%r",
            msg.channel,
            msg.sender,
            msg.text,
        )
        self.translation_manager.enqueue(MessageContext.from_chat_message(msg))

    def on_outgoing_message(self, text: str):
        text = str(text or "").strip()
        if not text:
            self.logger.debug("Empty outgoing message ignored.")
            return

        prefix = text[0] if text[0] in OUTGOING_CHANNELS else ""
        channel, channel_symbol = OUTGOING_CHANNELS.get(prefix, ("local", ""))

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

    def on_message_ready(self, context: MessageContext):
        self.logger.info(
            "Translation completed: text=%r provider=%r direction=%r",
            context.display_text,
            context.provider,
            context.direction,
        )

        is_outgoing = context.direction is not None and str(context.direction).strip().lower() in {
            "outgoing", "out", "send", "sent", "to", "кому",
        }

        if is_outgoing:
            prepared_text = context.display_text or context.original_text
            is_local = str(context.channel or "").strip().lower() == "local"
            self.logger.info(
                "OUTGOING -> GameChatSender.send(): %r local=%s",
                prepared_text,
                is_local,
            )
            sent = self.game_chat_sender.send(prepared_text, local=is_local)
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

    def on_translation_failed(self, context: MessageContext, error: str):
        self.logger.error(
            "Translation failed: original=%r error=%r direction=%r",
            context.original_text,
            error,
            context.direction,
        )

        is_outgoing = context.direction is not None and str(context.direction).strip().lower() in {
            "outgoing", "out", "send", "sent", "to", "кому",
        }

        if is_outgoing:
            is_local = str(context.channel or "").strip().lower() == "local"
            self.logger.warning(
                "OUTGOING FALLBACK -> GameChatSender.send(): %r local=%s",
                context.original_text,
                is_local,
            )
            sent = self.game_chat_sender.send(context.original_text, local=is_local)
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

    def on_log_status(self, status: str):
        self.logger.info("LogReader: %s", status)

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

        self.logger.info("Qt event loop finished with exit code %s.", ret)
        self.log_reader.stop()
        self.translation_manager.stop()
        try:
            self.hotkey_manager.stop()
        except Exception:
            self.logger.exception("Error while stopping configured hotkeys.")
        sys.exit(ret)


if __name__ == "__main__":
    logger = setup_logging()
    try:
        log_settings_snapshot(config.data, logger=get_logger("Settings"))
        app = ExilingoApp()
        app.run()
    except SystemExit:
        raise
    except Exception:
        log_exception(logger, "Unhandled exception at application top level.")
        raise
    finally:
        shutdown_logging()
