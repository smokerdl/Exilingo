"""Exilingo chat-channel display filters."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from core.config_manager import config


CHAT_FILTER_CHANNELS = [
    ("local", "Область"),
    ("global", "Общий"),
    ("party", "Группа"),
    ("whisper", "Личные"),
    ("trade", "Торговый"),
    ("guild", "Гильдия"),
]


class ChatChannelFilterBar(QWidget):
    """Manual channel filters that mirror the PoE chat filter buttons."""

    channel_filter_changed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = {}
        self._build_ui()
        self.load_state()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for channel_id, title in CHAT_FILTER_CHANNELS:
            button = QPushButton(title, self)
            button.setCheckable(True)
            button.setObjectName("ChatChannelButton")
            button.setProperty("channel_id", channel_id)
            button.setToolTip(f"Показывать канал: {title}")
            button.clicked.connect(
                lambda checked, current_channel=channel_id: self._on_button_clicked(
                    current_channel,
                    checked,
                )
            )
            button.setMinimumHeight(26)
            self._buttons[channel_id] = button
            layout.addWidget(button, 1)

        self.setObjectName("ChatChannelFilterBar")
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(
            """
            QWidget#ChatChannelFilterBar {
                background: transparent;
            }

            QPushButton#ChatChannelButton {
                min-width: 0px;
                padding: 3px 8px;
                border: 1px solid #5A4325;
                border-radius: 2px;
                color: #77736A;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #252525,
                    stop: 0.5 #171717,
                    stop: 1 #101010
                );
                font-family: Segoe UI;
                font-size: 11px;
                font-weight: normal;
            }

            QPushButton#ChatChannelButton:hover {
                color: #D0AE72;
                border-color: #8C6C36;
            }

            QPushButton#ChatChannelButton:checked {
                color: #D99A2B;
                border-color: #9B6A25;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2D2A24,
                    stop: 0.5 #201B14,
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

    def load_state(self):
        for channel_id, _title in CHAT_FILTER_CHANNELS:
            self._buttons[channel_id].setChecked(
                config.chat_channel_enabled(channel_id)
            )

    def _on_button_clicked(self, channel_id: str, enabled: bool):
        config.set_chat_channel_enabled(channel_id, enabled)
        self.channel_filter_changed.emit(channel_id, enabled)

    def is_channel_enabled(self, channel_id: str) -> bool:
        button = self._buttons.get(channel_id)
        if button is None:
            return True
        return button.isChecked()

    def set_all_enabled(self, enabled: bool):
        for channel_id, _title in CHAT_FILTER_CHANNELS:
            button = self._buttons[channel_id]
            button.setChecked(enabled)
            config.set_chat_channel_enabled(channel_id, enabled)
            self.channel_filter_changed.emit(channel_id, enabled)
