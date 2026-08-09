from __future__ import annotations

import sys
import os
import json
import ctypes

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSignal as Signal, QObject, pyqtSlot, QEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QApplication,
    QSizeGrip,
    QComboBox,
)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
CONFIG_FILE = "config.json"

CHAT_CHANNELS = [
    ("local", "Local - Область", ""),
    ("global", "Global - Общий", "#"),
    ("party", "Party - Группа", "%"),
    ("whisper", "Whisper - Личный", "@"),
    ("trade", "Trade - Торговля", "$"),
    ("guild", "Guild - Гильдия", "&"),
]
CHAT_PREFIXES = {prefix for _, _, prefix in CHAT_CHANNELS if prefix}
CHAT_NAME_COLORS = {
    "": "#33CC66",  # Local - green
    "#": "#FF3333",  # Global - red
    "$": "#FF9933",  # Trade - orange
    "%": "#6699FF",  # Party - blue
    "@": "#CC66FF",  # Whisper - purple
    "&": "#A0A0A0",  # Guild - gray
}


class GlobalHotkeyListener(QObject):
    toggle_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        try:
            import keyboard

            keyboard.add_hotkey("enter", self._on_enter_pressed)
        except Exception as e:
            print(f"[HotkeyError] Не удалось зарегистрировать клавишу: {e}")

    def _on_enter_pressed(self):
        self.toggle_requested.emit()


class ChatOverlay(QWidget):
    settings_requested = Signal()
    close_requested = Signal()
    send_message_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._old_pos = None
        self.is_input_mode = False
        self.font_size = 15
        self.init_ui()
        self.load_config()
        self.set_input_mode(False)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(500, 250)
        self.setMinimumSize(280, 120)

        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("MainFrame")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_frame)

        self.frame_layout = QVBoxLayout(self.main_frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)

        self.header_widget = QWidget(self)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(4, 2, 4, 4)

        self.title_label = QLabel("<b>EXILINGO CHAT</b>", self)
        self.title_label.setStyleSheet("color: #AF9870; font-size: 11px;")

        self.settings_button = QPushButton("⚙", self)
        self.settings_button.setObjectName("HeaderBtn")
        self.settings_button.setFixedSize(22, 22)
        self.settings_button.setToolTip("Настройки Exilingo")
        self.settings_button.clicked.connect(self.settings_requested.emit)

        self.close_button = QPushButton("✕", self)
        self.close_button.setObjectName("HeaderBtn")
        self.close_button.setFixedSize(22, 22)
        self.close_button.setToolTip("Закрыть оверлей")
        self.close_button.clicked.connect(self.close_requested.emit)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.settings_button)
        header_layout.addWidget(self.close_button)

        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)

        self.input_widget = QWidget(self)
        input_layout = QHBoxLayout(self.input_widget)
        input_layout.setContentsMargins(0, 4, 0, 0)

        self.channel_combo = QComboBox(self)
        self.channel_combo.setMinimumWidth(150)
        self.channel_combo.setToolTip(
            "Выберите канал, в который будет отправлено сообщение"
        )
        for channel_id, title, prefix in CHAT_CHANNELS:
            self.channel_combo.addItem(title, channel_id)
        self.channel_combo.setCurrentIndex(0)
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Введите сообщение...")
        self.input_field.returnPressed.connect(self._on_send)

        self.send_btn = QPushButton("Отправить", self)
        self.send_btn.clicked.connect(self._on_send)

        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)

        input_layout.addWidget(self.channel_combo)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(
            self.size_grip,
            0,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
        )

        self.frame_layout.addWidget(self.header_widget)
        self.frame_layout.addWidget(self.chat_history)
        self.frame_layout.addWidget(self.input_widget)

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            geo = data.get("overlay_geometry", {})
            if not geo:
                overlay = data.get("overlay", {})
                if isinstance(overlay, dict):
                    geo = overlay.get("geometry", {})

            if all(key in geo for key in ("x", "y", "w", "h")):
                self.setGeometry(
                    int(geo["x"]), int(geo["y"]), int(geo["w"]), int(geo["h"])
                )

            if "font_size" in data:
                self.font_size = int(data["font_size"])
            else:
                overlay = data.get("overlay", {})
                if isinstance(overlay, dict):
                    self.font_size = int(overlay.get("font_size", 13))
        except Exception as e:
            print(f"[ConfigError] Не удалось загрузить конфиг: {e}")

    def save_config(self):
        config_data = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception:
                config_data = {}

        geometry = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}
        config_data["overlay_geometry"] = geometry
        config_data["font_size"] = self.font_size

        overlay = config_data.setdefault("overlay", {})
        if not isinstance(overlay, dict):
            overlay = {}
            config_data["overlay"] = overlay
        overlay["geometry"] = geometry
        overlay["font_size"] = self.font_size

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigError] Не удалось сохранить конфиг: {e}")

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self.is_input_mode:
                self.set_input_mode(False)
        super().changeEvent(event)

    @pyqtSlot()
    def toggle_mode(self):
        self.set_input_mode(not self.is_input_mode)

    def set_input_mode(self, enabled: bool):
        if self.is_input_mode and not enabled:
            self.save_config()

        self.is_input_mode = enabled
        self._set_click_through(not enabled)

        if enabled:
            self.header_widget.show()
            self.input_widget.show()
            self.chat_history.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.main_frame.setStyleSheet(
                f"""QFrame#MainFrame {{ background-color: rgba(12,12,12,225); border: 1px solid #4A3B2C; border-radius: 2px; }} QTextEdit {{ background: transparent; color: #E0E0E0; border: none; font-family: Segoe UI; font-size: {self.font_size}px; }} QLineEdit {{ background: rgba(0,0,0,200); color: white; border: 1px solid #5C4A38; border-radius: 2px; padding: 4px; font-size: {self.font_size}px; }} QComboBox {{ background: rgba(0,0,0,200); color: white; border: 1px solid #5C4A38; border-radius: 2px; padding: 4px; font-size: {self.font_size}px; }} QComboBox QAbstractItemView {{ background: #17130F; color: white; border: 1px solid #5C4A38; selection-background-color: #3D3227; selection-color: #E8D4B3; }} QPushButton {{ background:#2B231B; color:#AF9870; border:1px solid #5C4A38; border-radius:2px; padding:4px 10px; font-weight:bold; }} QPushButton#HeaderBtn {{ padding: 0px; font-size: 14px; }} QPushButton:hover {{ background:#3D3227; color:#E8D4B3; }}"""
            )
            self.activateWindow()
            self.input_field.setFocus()
        else:
            self.header_widget.hide()
            self.input_widget.hide()
            self.chat_history.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self.main_frame.setStyleSheet(
                f"""QFrame#MainFrame {{ background: transparent; border:none; }} QTextEdit {{ background: transparent; color:#E0E0E0; border:none; font-family: Segoe UI; font-size:{self.font_size}px; }}"""
            )

    def set_font_size(self, size: int):
        self.font_size = size
        self.set_input_mode(self.is_input_mode)
        self.save_config()

    def _set_click_through(self, click_through: bool):
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if click_through:
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.set_input_mode(False)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.is_input_mode and event.button() == Qt.MouseButton.LeftButton:
            self._old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if (
            self.is_input_mode
            and self._old_pos is not None
            and event.buttons() == Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._old_pos = None
            if self.is_input_mode:
                self.save_config()

    def _channel_prefix(self, channel_id: str) -> str:
        for current_channel_id, _title, prefix in CHAT_CHANNELS:
            if current_channel_id == channel_id:
                return prefix
        return ""

    def _on_channel_changed(self, _index: int):
        """При смене канала полностью сбрасывает старое содержимое и ставит префикс нового канала."""
        prefix = self._channel_prefix(self.channel_combo.currentData())
        self.input_field.setText(f"{prefix}" if prefix else "")
        self.input_field.setCursorPosition(len(self.input_field.text()))

    def _prepare_outgoing_message(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text[0] in CHAT_PREFIXES:
            return text
        channel_id = self.channel_combo.currentData()
        prefix = self._channel_prefix(channel_id)
        return prefix + text if prefix else text

    def _extract_whisper_target(self, text: str) -> str:
        """Возвращает никнейм из Whisper-строки, если он присутствует."""
        text = text.strip()
        if not text:
            return ""
        if text.startswith("@"):
            text = text[1:].lstrip()
        if not text:
            return ""
        return text.split(None, 1)[0]

    def _whisper_input_after_send(self, text: str) -> str:
        """Оставляет никнейм с @ и обязательный пробел после отправки Whisper."""
        target = self._extract_whisper_target(text)
        if not target:
            return ""
        return f"@{target} "

    def _on_send(self):
        raw_text = self.input_field.text()
        text = raw_text.strip()
        if not text:
            self.set_input_mode(False)
            return

        channel_id = self.channel_combo.currentData()
        prepared_text = self._prepare_outgoing_message(text)
        if not prepared_text:
            self.set_input_mode(False)
            return

        print("[ChatOverlay] Исходящее сообщение:", prepared_text)
        self.send_message_requested.emit(prepared_text)

        if channel_id == "whisper":
            self.input_field.setText(self._whisper_input_after_send(prepared_text))
        else:
            prefix = self._channel_prefix(channel_id)
            self.input_field.setText(f"{prefix}" if prefix else "")

        self.input_field.setCursorPosition(len(self.input_field.text()))
        self.set_input_mode(False)

    def add_message(
        self, channel_prefix: str, sender: str, text: str, is_translated: bool = True
    ):
        text_color = "#FFD700" if is_translated else "#A0A0A0"
        name_color = CHAT_NAME_COLORS.get(channel_prefix, "#E0E0E0")
        html = f"""<div style="margin-bottom:4px; text-shadow:1px 1px 2px black;"><span style="color:{name_color}; font-weight:bold;">{channel_prefix}{sender}: </span><span style="color:{text_color};">{text}</span></div>"""
        self.chat_history.append(html)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatOverlay()
    window.send_message_requested.connect(
        lambda text: print(f"[TEST] Будет отправлено в PoE: {text}")
    )
    window.add_message("#", "DageTheEvil", "Продаю тому, кто предложит больше всех")
    window.add_message("#", "Prawny", "Почему 67 — это смешно?")
    window.add_message(
        "#", "SummonRagingSychoSid", "SRS на самом деле требуют нажатия кнопок"
    )
    window.show()
    hotkey_listener = GlobalHotkeyListener()
    hotkey_listener.toggle_requested.connect(window.toggle_mode)
    sys.exit(app.exec())
