"""Manual chat-channel filters for the Exilingo overlay.

The filter state belongs to Exilingo, not to Path of Exile. LatestClient.txt
contains chat messages regardless of which PoE chat buttons are currently
visible, so this module provides the local display filter and applies it
before messages enter the translation queue.
"""

from __future__ import annotations

from core.config_manager import config
from core.translation_manager import TranslationManager
from ui.chat_overlay import ChatOverlay


CHAT_FILTER_CHANNELS = (
    ("local", "Область"),
    ("global", "Общий"),
    ("party", "Группа"),
    ("whisper", "Личные"),
    ("trade", "Торговый"),
    ("guild", "Гильдия"),
)
CHAT_FILTER_IDS = frozenset(channel_id for channel_id, _title in CHAT_FILTER_CHANNELS)


def _channel_enabled(channel_id: str) -> bool:
    if channel_id not in CHAT_FILTER_IDS:
        return True
    return bool(config.get("chat_filters", channel_id, default=True))


def _set_channel_enabled(channel_id: str, enabled: bool) -> None:
    if channel_id not in CHAT_FILTER_IDS:
        return
    config.set("chat_filters", channel_id, value=bool(enabled))


class _ChatChannelFilterMixin:
    """Methods mixed into ChatOverlay by the runtime patch."""

    def is_chat_channel_enabled(self, channel_id: str) -> bool:
        return _channel_enabled(channel_id)

    def set_chat_channel_enabled(self, channel_id: str, enabled: bool) -> None:
        _set_channel_enabled(channel_id, enabled)
        bar = getattr(self, "chat_channel_filter_bar", None)
        if bar is not None:
            button = bar.button_for_channel(channel_id)
            if button is not None and button.isChecked() != bool(enabled):
                button.setChecked(bool(enabled))


class ChatChannelFilterBar(__import__("PyQt6.QtWidgets", fromlist=["QWidget"]).QWidget):
    """PoE-like channel filter buttons for interactive Exilingo mode."""

    def __init__(self, parent=None):
        from PyQt6.QtCore import pyqtSignal
        from PyQt6.QtWidgets import QHBoxLayout, QPushButton

        # Signals are stored on the instance to avoid introducing another
        # import-time QObject subclass dependency in the patch module.
        super().__init__(parent)
        self._buttons = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        for channel_id, title in CHAT_FILTER_CHANNELS:
            button = QPushButton(title, self)
            button.setCheckable(True)
            button.setObjectName("ChatChannelButton")
            button.setMinimumHeight(25)
            button.setToolTip(f"Показывать канал: {title}")
            button.clicked.connect(
                lambda checked, current_channel=channel_id: self._on_clicked(
                    current_channel,
                    checked,
                )
            )
            self._buttons[channel_id] = button
            layout.addWidget(button, 1)

        self.setObjectName("ChatChannelFilterBar")
        self.setStyleSheet(
            """
            QWidget#ChatChannelFilterBar {
                background: transparent;
            }
            QPushButton#ChatChannelButton {
                min-width: 0px;
                padding: 2px 7px;
                border: 1px solid #594326;
                border-radius: 2px;
                color: #77736A;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #292929,
                    stop: 0.45 #1B1B1B,
                    stop: 1 #111111
                );
                font-family: Segoe UI;
                font-size: 10px;
            }
            QPushButton#ChatChannelButton:hover {
                color: #D8B36C;
                border-color: #8C6C36;
            }
            QPushButton#ChatChannelButton:checked {
                color: #D99A2B;
                border-color: #9B6A25;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #302C25,
                    stop: 0.45 #211C15,
                    stop: 1 #15120E
                );
                font-weight: bold;
            }
            QPushButton#ChatChannelButton:checked:hover {
                color: #F0C56A;
                border-color: #C18A35;
            }
            """
        )
        self.load_state()

    def button_for_channel(self, channel_id: str):
        return self._buttons.get(channel_id)

    def load_state(self):
        for channel_id, _title in CHAT_FILTER_CHANNELS:
            button = self._buttons[channel_id]
            button.setChecked(_channel_enabled(channel_id))

    def _on_clicked(self, channel_id: str, enabled: bool):
        _set_channel_enabled(channel_id, enabled)


def _patch_overlay() -> None:
    if getattr(ChatOverlay, "_chat_channel_filter_patched", False):
        return

    original_init_ui = ChatOverlay.init_ui
    original_set_input_mode = ChatOverlay.set_input_mode

    def patched_init_ui(self):
        original_init_ui(self)
        self.chat_channel_filter_bar = ChatChannelFilterBar(self)
        self.frame_layout.insertWidget(1, self.chat_channel_filter_bar)

    def patched_set_input_mode(self, enabled: bool):
        original_set_input_mode(self, enabled)
        bar = getattr(self, "chat_channel_filter_bar", None)
        if bar is not None:
            bar.setVisible(bool(enabled))

    ChatOverlay.init_ui = patched_init_ui
    ChatOverlay.set_input_mode = patched_set_input_mode
    ChatOverlay.is_chat_channel_enabled = _ChatChannelFilterMixin.is_chat_channel_enabled
    ChatOverlay.set_chat_channel_enabled = _ChatChannelFilterMixin.set_chat_channel_enabled
    ChatOverlay._chat_channel_filter_patched = True


def _patch_translation_manager() -> None:
    if getattr(TranslationManager, "_chat_channel_filter_patched", False):
        return

    original_enqueue = TranslationManager.enqueue

    def patched_enqueue(self, context):
        # LatestClient messages are incoming for Exilingo. Outgoing messages
        # are created by the overlay and must never be blocked by display filters.
        if context.direction is None and context.channel in CHAT_FILTER_IDS:
            if not _channel_enabled(context.channel):
                self.logger.debug(
                    "chat channel filtered: channel=%r sender=%r text=%r",
                    context.channel,
                    context.sender,
                    context.original_text,
                )
                return

        return original_enqueue(self, context)

    TranslationManager.enqueue = patched_enqueue
    TranslationManager._chat_channel_filter_patched = True


_patch_overlay()
_patch_translation_manager()
