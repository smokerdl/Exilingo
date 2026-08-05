import sys
import os
import json
import ctypes
from PyQt6.QtCore import Qt, pyqtSignal, QObject, pyqtSlot, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel, QFrame, QApplication, QSizeGrip
)

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
CONFIG_FILE = "config.json"


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
    send_message_requested = pyqtSignal(str)
    open_settings_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._old_pos = None
        self.is_input_mode = False
        self.font_size = 13
        
        self.init_ui()
        self.load_config()
        self.set_input_mode(False)

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(500, 250)
        self.setMinimumSize(280, 120)

        # Главный контейнер
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("MainFrame")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.main_frame)

        self.frame_layout = QVBoxLayout(self.main_frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)

        # --- 1. Шапка ---
        self.header_widget = QWidget(self)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(4, 2, 4, 4)

        self.title_label = QLabel("<b>EXILINGO CHAT</b>", self)
        self.title_label.setStyleSheet("color: #AF9870; font-size: 11px;")
        
        self.settings_btn = QPushButton("⚙", self)
        self.settings_btn.setFixedSize(22, 22)
        self.settings_btn.setToolTip("Настройки Exilingo")
        self.settings_btn.clicked.connect(self.open_settings_requested.emit)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.settings_btn)

        # --- 2. История сообщений ---
        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)

        # --- 3. Панель ввода + Уголок масштабирования ---
        self.input_widget = QWidget(self)
        input_layout = QHBoxLayout(self.input_widget)
        input_layout.setContentsMargins(0, 4, 0, 0)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Нажмите Enter и введите сообщение...")
        self.input_field.returnPressed.connect(self._on_send)

        self.send_btn = QPushButton("Отправить", self)
        self.send_btn.clicked.connect(self._on_send)

        # Единственный функциональный маркер масштабирования
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        input_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        self.frame_layout.addWidget(self.header_widget)
        self.frame_layout.addWidget(self.chat_history)
        self.frame_layout.addWidget(self.input_widget)

    # --- Чтение и сохранение конфигурации (config.json) ---
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    geo = data.get("overlay_geometry", {})
                    if all(k in geo for k in ("x", "y", "w", "h")):
                        self.setGeometry(geo["x"], geo["y"], geo["w"], geo["h"])
                    if "font_size" in data:
                        self.font_size = data["font_size"]
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

        config_data["overlay_geometry"] = {
            "x": self.x(),
            "y": self.y(),
            "w": self.width(),
            "h": self.height()
        }
        config_data["font_size"] = self.font_size

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ConfigError] Не удалось сохранить конфиг: {e}")

    # --- Обработка фокуса окна (Клик вне оверлея) ---
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
            # РЕЖИМ ВВОДА
            self.header_widget.show()
            self.input_widget.show()
            self.chat_history.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            
            self.main_frame.setStyleSheet(f"""
                QFrame#MainFrame {{
                    background-color: rgba(12, 12, 12, 225);
                    border: 1px solid #4A3B2C;
                    border-radius: 2px;
                }}
                QTextEdit {{
                    background-color: transparent;
                    color: #E0E0E0;
                    border: none;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: {self.font_size}px;
                }}
                QLineEdit {{
                    background-color: rgba(0, 0, 0, 200);
                    color: #FFFFFF;
                    border: 1px solid #5C4A38;
                    border-radius: 2px;
                    padding: 4px;
                    font-size: {self.font_size}px;
                }}
                QPushButton {{
                    background-color: #2B231B;
                    color: #AF9870;
                    border: 1px solid #5C4A38;
                    border-radius: 2px;
                    padding: 4px 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #3D3227;
                    color: #E8D4B3;
                }}
                QSizeGrip {{
                    width: 16px;
                    height: 16px;
                }}
            """)
            self.activateWindow()
            self.input_field.setFocus()
        else:
            # РЕЖИМ ВЫВОДА
            self.header_widget.hide()
            self.input_widget.hide()
            self.chat_history.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
            self.main_frame.setStyleSheet(f"""
                QFrame#MainFrame {{
                    background-color: transparent;
                    border: none;
                }}
                QTextEdit {{
                    background-color: transparent;
                    color: #E0E0E0;
                    border: none;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: {self.font_size}px;
                }}
            """)

    def set_font_size(self, size: int):
        self.font_size = size
        self.set_input_mode(self.is_input_mode)
        self.save_config()

    def _set_click_through(self, click_through: bool):
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        if click_through:
            style |= (WS_EX_TRANSPARENT | WS_EX_LAYERED)
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
        if self.is_input_mode and self._old_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._old_pos = None
            if self.is_input_mode:
                self.save_config()

    def add_message(self, channel_prefix: str, sender: str, text: str, is_translated: bool = True):
        text_color = "#FFD700" if is_translated else "#A0A0A0"
        
        html = f"""
        <div style="margin-bottom: 4px; text-shadow: 1px 1px 2px #000000;">
            <span style="color: #2EB82E;">(12)</span> 
            <span style="color: #FF3333; font-weight: bold;">{channel_prefix}{sender}:</span> 
            <span style="color: {text_color};">{text}</span>
        </div>
        """
        self.chat_history.append(html)

    def _on_send(self):
        text = self.input_field.text().strip()
        if text:
            self.send_message_requested.emit(text)
            self.input_field.clear()
        self.set_input_mode(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ChatOverlay()
    
    window.add_message("#", "DageTheEvil", "Продаю тому, кто предложит больше всех")
    window.add_message("#", "Prawny", "Почему 67 — это смешно?")
    window.add_message("#", "SummonRagingSychoSid", "SRS на самом деле требуют нажатия кнопок")
    
    window.show()

    hotkey_listener = GlobalHotkeyListener()
    hotkey_listener.toggle_requested.connect(window.toggle_mode)

    sys.exit(app.exec())