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
from ui.global_mouse_listener import GlobalMouseListener


OUTGOING_CHANNELS = {
    "": ("local", ""),
    "#": ("global", "#"),
    "%": ("party", "%"),
    "@": ("whisper", "@"),
    "$": ("trade", "$"),
    "&": ("guild", "&"),
}


class _InputSignals(QObject):
    """Marshals callbacks from global input threads onto the Qt thread."""

    send_message = pyqtSignal()
    toggle_mode = pyqtSignal()
    toggle_visibility = pyqtSignal()
    left_click = pyqtSignal(int, int)


class ExilingoApp:
    def __init__(self):
        self.logger = get_logger("Main")
        self._startup_cancelled = False
        self.log_reader = None

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

        self.input_signals = _InputSignals()
        self.input_signals.send_message.connect(self.overlay._on_send)
        self.input_signals.toggle_mode.connect(self.on_toggle_overlay_mode)
        self.input_signals.toggle_visibility.connect(self.on_toggle_overlay_visibility)

        self.hotkey_manager = HotkeyManager(
            {
                "send_message": self.input_signals.send_message.emit,
                "toggle_mode": self.input_signals.toggle_mode.emit,
                "toggle_visibility": self.input_signals.toggle_visibility.emit,
            }
        )
        set_runtime_callbacks(self._apply_runtime_settings, self.hotkey_manager.reload)

        self.mouse_listener = GlobalMouseListener()
        self.mouse_listener.left_click.connect(self.input_signals.left_click.emit)
        self.input_signals.left_click.connect(self._on_global_left_click)
        self.mouse_listener.start()
        self.logger.info("Global mouse listener started.")

        if not config.log_path:
            self.logger.warning(
                "Path of Exile log path is not configured. Opening settings for first-time setup."
            )
            self._open_settings_dialog()

        log_path = config.log_path
        if not log_path:
            self.logger.info("Startup cancelled: Path of Exile log path is still not configured.")
            self._startup_cancelled = True
            self._stop_background_components()
            return

        self.logger.info("Using Path of Exile log path: %s", log_path)
        self._ensure_log_reader(log_path)

    # =======================================================
    # Global mouse / overlay mode
    # =======================================================

    def _on_global_left_click(self, x: int, y: int):
        """Switch interactive overlay to click-through on an outside LMB."""
        if not self.overlay.is_input_mode:
            return

        if self.overlay.is_global_point_inside_interactive_area(x, y):
            return

        geometry = self.overlay.geometry()
        popup_geometry = self.overlay.interactive_popup_geometry()
        popup_text = "none"
        if popup_geometry is not None:
            popup_text = (
                f"({popup_geometry.x()},{popup_geometry.y()},"
                f"{popup_geometry.width()},{popup_geometry.height()})"
            )

        self.logger.info(
            "Outside LMB -> interactive -> click-through: cursor=(%d,%d) "
            "overlay=(%d,%d,%d,%d) channel_popup=%s",
            x,
            y,
            geometry.x(),
            geometry.y(),
            geometry.width(),
            geometry.height(),
            popup_text,
        )
        self.on_toggle_overlay_mode()

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
    # Startup/runtime helpers
    # =======================================================

    def _ensure_log_reader(self, log_path: str):
        """Create the LogReader once a valid path becomes available."""
        if self.log_reader is not None:
            if self.log_reader.log_filepath != log_path:
                if self.log_reader.isRunning():
                    self.log_reader.stop()
                self.log_reader = None
            else:
                return

        self.logger.info("Preparing LogReader for Path of Exile log path: %s", log_path)
        self.log_reader = LogReaderThread(
            log_filepath=log_path,
            read_from_end=True,
        )
        self.log_reader.new_chat_message.connect(self.on_new_chat_message)
        self.log_reader.window_focus_changed.connect(self.on_game_focus_changed)
        self.log_reader.status_changed.connect(self.on_log_status)

    # =======================================================
    # Shutdown / settings
    # =======================================================

    def _stop_background_components(self):
        """Stop components that may already have been started during startup."""
        log_reader = getattr(self, "log_reader", None)
        if log_reader is not None:
            try:
                log_reader.stop()
            except Exception:
                self.logger.exception("Error while stopping LogReader.")

        translation_manager = getattr(self, "translation_manager", None)
        if translation_manager is not None:
            try:
                translation_manager.stop()
            except Exception:
                self.logger.exception("Error while stopping translation worker.")

        mouse_listener = getattr(self, "mouse_listener", None)
        if mouse_listener is not None:
            try:
                mouse_listener.stop()
            except Exception:
                self.logger.exception("Error while stopping global mouse listener.")

        hotkey_manager = getattr(self, "hotkey_manager", None)
        if hotkey_manager is not None:
            try:
                hotkey_manager.stop()
            except Exception:
                self.logger.exception("Error while stopping configured hotkeys.")

        tray_icon = getattr(self, "tray_icon", None)
        if tray_icon is not None:
            try:
                tray_icon.hide()
            except Exception:
                self.logger.exception("Error while hiding system tray icon.")

    def close_application(self):
        self.logger.info("Application shutdown requested.")
        self._stop_background_components()
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

        # First-run settings are a nested modal dialog inside ExilingoApp.__init__.
        # When Apply is pressed, the dialog must be able to make a newly entered
        # log path available immediately, without waiting for the dialog to close.
        if config.log_path:
            self._ensure_log_reader(config.log_path)

    def _open_settings_dialog(self):
        self.logger.info("Settings window opened.")
        try:
            dialog = SettingsDialog(self.overlay)
            dialog.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
            )
            accepted = dialog.exec() == dialog.DialogCode.Accepted
            if config.log_path:
                self._apply_runtime_settings()
            if accepted:
                self.logger.info("Settings saved.")
            else:
                self.logger.info("Settings closed without further changes.")
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
        if self._startup_cancelled:
            self.logger.info("Startup cancelled by user; exiting cleanly.")
            return

        if self.log_reader is None:
            self.logger.error("Cannot start application: LogReader is not configured.")
            self._startup_cancelled = True
            self._stop_background_components()
            return

        if not self.log_reader.isRunning():
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
        self._stop_background_components()
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
