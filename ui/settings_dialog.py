from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import config, DEFAULT_CONFIG
from core.provider_registry import ProviderRegistry


# ============================================================
# Каналы маршрутизации
# ============================================================

ROUTING_CHANNELS = [
    ("global", "Global - Общий"),
    ("local", "Local - Область"),
    ("trade", "Trade - Торговля"),
    ("party", "Party - Группа"),
    ("guild", "Guild - Гильдия"),
    ("whisper", "Whisper - Личный"),
]


# ============================================================
# Игровые каналы
# ============================================================

CHAT_CHANNELS = [
    ("local", "Local - Область", ""),
    ("global", "Global - Общий", "#"),
    ("party", "Party - Группа", "%"),
    ("whisper", "Whisper - Личный", "@"),
    ("trade", "Trade - Торговля", "$"),
    ("guild", "Guild - Гильдия", "&"),
]


# ============================================================
# Провайдеры
# ============================================================

PROVIDER_NAMES = {
    "google": "Google Translate",
    "gemini": "Gemini",
    "openrouter": "OpenRouter",
    "ollama": "Ollama",
}


AI_PROVIDERS = (
    "gemini",
    "openrouter",
    "ollama",
)


# ============================================================
# Settings Dialog
# ============================================================


class SettingsDialog(QDialog):
    """
    Главное окно настроек Exilingo.

    Вкладки:

        Общие
        Overlay
        Переводчики
        Маршрутизация
    """

    CALIBRATION_DELAY = 3

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Exilingo - Настройки")
        self.setMinimumSize(820, 650)

        self.registry = ProviderRegistry()

        self.current_provider_id: Optional[str] = None
        self.current_routing_channel: Optional[str] = None

        self.routing_data: Dict[str, List[str]] = {}

        self.calibration_timer: Optional[QTimer] = None
        self.calibration_seconds = 0

        self._build_ui()
        self._apply_style()
        self._load_all_settings()

    # ========================================================
    # Основной UI
    # ========================================================

    def _build_ui(self):

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        main_layout.setSpacing(8)

        self.tabs = QTabWidget()

        main_layout.addWidget(
            self.tabs,
        )

        # ----------------------------------------------------
        # Вкладки
        # ----------------------------------------------------

        self._build_general_tab()
        self._build_overlay_tab()
        self._build_providers_tab()
        self._build_routing_tab()

        # ----------------------------------------------------
        # Нижние кнопки
        # ----------------------------------------------------

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        buttons.accepted.connect(
            self._save_and_accept,
        )

        buttons.rejected.connect(
            self.reject,
        )

        main_layout.addWidget(
            buttons,
        )

    # ========================================================
    # Общий стиль
    # ========================================================

    def _apply_style(self):

        self.setStyleSheet(
            """
            QDialog {
                background-color: #0C0C0C;
                color: #E0E0E0;
                font-family: "Segoe UI";
                font-size: 13px;
            }

            QWidget {
                color: #E0E0E0;
            }

            QTabWidget::pane {
                background: #0C0C0C;
                border: 1px solid #4A3B2C;
                border-radius: 2px;
            }

            QTabBar::tab {
                background: #17130F;
                color: #AF9870;
                border: 1px solid #4A3B2C;
                padding: 7px 14px;
                margin-right: 2px;
            }

            QTabBar::tab:selected {
                background: #2B231B;
                color: #E8D4B3;
                border-bottom-color: #2B231B;
            }

            QTabBar::tab:hover {
                background: #3D3227;
                color: #E8D4B3;
            }

            QGroupBox {
                background: #11100E;
                border: 1px solid #4A3B2C;
                border-radius: 2px;
                margin-top: 10px;
                padding: 10px;
                font-weight: bold;
                color: #AF9870;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #AF9870;
            }

            QLabel {
                color: #D0C4B4;
            }

            QLineEdit,
            QPlainTextEdit,
            QSpinBox,
            QComboBox,
            QListWidget {
                background-color: #0F0F0F;
                color: #E0E0E0;
                border: 1px solid #5C4A38;
                border-radius: 2px;
                padding: 4px;
                selection-background-color: #3D3227;
                selection-color: #E8D4B3;
            }

            QLineEdit:focus,
            QPlainTextEdit:focus,
            QSpinBox:focus,
            QComboBox:focus,
            QListWidget:focus {
                border: 1px solid #AF9870;
            }

            QComboBox QAbstractItemView {
                background: #17130F;
                color: #E0E0E0;
                border: 1px solid #5C4A38;
                selection-background-color: #3D3227;
                selection-color: #E8D4B3;
            }

            QListWidget::item {
                padding: 7px;
            }

            QListWidget::item:selected {
                background: #3D3227;
                color: #E8D4B3;
            }

            QPushButton {
                background: #2B231B;
                color: #AF9870;
                border: 1px solid #5C4A38;
                border-radius: 2px;
                padding: 5px 12px;
                font-weight: bold;
            }

            QPushButton:hover {
                background: #3D3227;
                color: #E8D4B3;
            }

            QPushButton:pressed {
                background: #211A15;
            }

            QDialogButtonBox QPushButton {
                min-width: 90px;
            }

            QCheckBox {
                color: #D0C4B4;
                spacing: 6px;
            }

            QScrollBar:vertical {
                background: #0C0C0C;
                width: 10px;
                margin: 0;
            }

            QScrollBar::handle:vertical {
                background: #4A3B2C;
                min-height: 25px;
                border-radius: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background: #5C4A38;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }

            QToolTip {
                background: #17130F;
                color: #E8D4B3;
                border: 1px solid #5C4A38;
            }
            """
        )

    # ========================================================
    # Общие
    # ========================================================

    def _build_general_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ----------------------------------------------------
        # Path of Exile
        # ----------------------------------------------------

        poe_group = QGroupBox(
            "Path of Exile",
        )

        form = QFormLayout(
            poe_group,
        )

        self.log_path_edit = QLineEdit()

        self.log_path_edit.setPlaceholderText(
            r"C:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt"
        )

        browse_button = QPushButton(
            "Обзор...",
        )

        browse_button.clicked.connect(
            self._browse_log_file,
        )

        path_layout = QHBoxLayout()

        path_layout.addWidget(
            self.log_path_edit,
        )

        path_layout.addWidget(
            browse_button,
        )

        form.addRow(
            "LatestClient.txt:",
            path_layout,
        )

        layout.addWidget(
            poe_group,
        )

        # ----------------------------------------------------
        # Игровой чат
        # ----------------------------------------------------

        chat_group = QGroupBox(
            "Отправка сообщений в игровой чат",
        )

        chat_form = QFormLayout(
            chat_group,
        )

        self.game_chat_x = QSpinBox()
        self.game_chat_x.setRange(
            -10000,
            10000,
        )

        self.game_chat_y = QSpinBox()
        self.game_chat_y.setRange(
            -10000,
            10000,
        )

        chat_form.addRow(
            "X:",
            self.game_chat_x,
        )

        chat_form.addRow(
            "Y:",
            self.game_chat_y,
        )

        self.calibration_status = QLabel(
            "Точка не настроена.",
        )

        self.calibration_status.setWordWrap(
            True,
        )

        calibration_button = QPushButton(
            "Калибровать точку...",
        )

        calibration_button.setToolTip(
            "Скрыть настройки на несколько секунд и записать текущую позицию курсора."
        )

        calibration_button.clicked.connect(
            self._start_calibration,
        )

        calibration_layout = QHBoxLayout()

        calibration_layout.addWidget(
            calibration_button,
        )

        calibration_layout.addWidget(
            self.calibration_status,
            1,
        )

        chat_form.addRow(
            "Точка:",
            calibration_layout,
        )

        layout.addWidget(
            chat_group,
        )

        # ----------------------------------------------------
        # Информация
        # ----------------------------------------------------

        info = QLabel(
            "Точка активации строки ввода сообщений игрового чата "
            "используется при отправке исходящих сообщений. "
            "Программа нажимает в эту точку, вставляет подготовленный "
            "текст и отправляет его клавишей Enter."
        )

        info.setWordWrap(
            True,
        )

        layout.addWidget(
            info,
        )

        info2 = QLabel(
            "Для калибровки нажмите кнопку, затем наведите курсор "
            "на строку ввода сообщений игрового чата. "
            "Через несколько секунд координаты будут сохранены."
        )

        info2.setWordWrap(
            True,
        )

        layout.addWidget(
            info2,
        )

        layout.addStretch()

        self.tabs.addTab(
            tab,
            "Общие",
        )

    # ========================================================
    # Калибровка точки
    # ========================================================

    def _start_calibration(self):

        if self.calibration_timer is not None:
            return

        self.calibration_seconds = self.CALIBRATION_DELAY

        self.calibration_status.setText(
            f"Наведите курсор на строку ввода. "
            f"Запись через {self.calibration_seconds}..."
        )

        self.setEnabled(
            False,
        )

        # Скрываем окно настроек, чтобы пользователь
        # мог увидеть игру и переместить курсор.
        self.hide()

        self.calibration_timer = QTimer(
            self,
        )

        self.calibration_timer.setInterval(
            1000,
        )

        self.calibration_timer.timeout.connect(
            self._calibration_tick,
        )

        self.calibration_timer.start()

    # --------------------------------------------------------

    def _calibration_tick(self):

        self.calibration_seconds -= 1

        if self.calibration_seconds > 0:
            self.calibration_status.setText(
                f"Наведите курсор на строку ввода. "
                f"Запись через {self.calibration_seconds}..."
            )

            return

        self.calibration_timer.stop()
        self.calibration_timer.deleteLater()
        self.calibration_timer = None

        position = QCursor.pos()

        x = position.x()
        y = position.y()

        self.game_chat_x.setValue(
            x,
        )

        self.game_chat_y.setValue(
            y,
        )

        self.calibration_status.setText(f"Точка записана: ({x}, {y})")

        self.setEnabled(
            True,
        )

        self.show()
        self.raise_()
        self.activateWindow()

    # ========================================================
    # Overlay
    # ========================================================

    def _build_overlay_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ----------------------------------------------------
        # Геометрия
        # ----------------------------------------------------

        geometry_group = QGroupBox(
            "Размер и положение",
        )

        geometry_form = QFormLayout(
            geometry_group,
        )

        self.overlay_x = QSpinBox()
        self.overlay_x.setRange(
            -10000,
            10000,
        )

        self.overlay_y = QSpinBox()
        self.overlay_y.setRange(
            -10000,
            10000,
        )

        self.overlay_width = QSpinBox()
        self.overlay_width.setRange(
            100,
            10000,
        )

        self.overlay_height = QSpinBox()
        self.overlay_height.setRange(
            50,
            10000,
        )

        geometry_form.addRow(
            "X:",
            self.overlay_x,
        )

        geometry_form.addRow(
            "Y:",
            self.overlay_y,
        )

        geometry_form.addRow(
            "Ширина:",
            self.overlay_width,
        )

        geometry_form.addRow(
            "Высота:",
            self.overlay_height,
        )

        layout.addWidget(
            geometry_group,
        )

        # ----------------------------------------------------
        # Размер шрифта
        # ----------------------------------------------------

        font_group = QGroupBox(
            "Шрифт",
        )

        font_form = QFormLayout(
            font_group,
        )

        self.font_size = QSpinBox()
        self.font_size.setRange(
            8,
            32,
        )

        font_form.addRow(
            "Размер:",
            self.font_size,
        )

        layout.addWidget(
            font_group,
        )

        # ----------------------------------------------------
        # Канал исходящих сообщений
        # ----------------------------------------------------

        outgoing_group = QGroupBox(
            "Канал исходящих сообщений",
        )

        outgoing_form = QFormLayout(
            outgoing_group,
        )

        self.outgoing_channel = QComboBox()

        for channel_id, title, prefix in CHAT_CHANNELS:
            self.outgoing_channel.addItem(
                title,
                channel_id,
            )

        outgoing_form.addRow(
            "Канал:",
            self.outgoing_channel,
        )

        layout.addWidget(
            outgoing_group,
        )

        layout.addStretch()

        self.tabs.addTab(
            tab,
            "Overlay",
        )

    # ========================================================
    # Провайдеры
    # ========================================================

    def _build_providers_tab(self):

        tab = QWidget()

        layout = QHBoxLayout(tab)

        self.provider_list = QListWidget()
        self.provider_stack = QTabWidget()
        self.provider_pages = {}

        self.provider_list.currentItemChanged.connect(
            self._provider_selected,
        )

        layout.addWidget(
            self.provider_list,
            1,
        )

        layout.addWidget(
            self.provider_stack,
            3,
        )

        # ----------------------------------------------------
        # Google Translate
        # ----------------------------------------------------

        google_page = QWidget()
        google_layout = QVBoxLayout(google_page)

        google_group = QGroupBox(
            "Google Translate",
        )

        google_form = QFormLayout(
            google_group,
        )

        google_enabled = QComboBox()
        google_enabled.addItem(
            "Выключен",
            False,
        )
        google_enabled.addItem(
            "Включен",
            True,
        )

        google_form.addRow(
            "Состояние:",
            google_enabled,
        )

        self.google_enabled = google_enabled

        google_source = QLineEdit()
        google_target = QLineEdit()

        google_form.addRow(
            "Язык входящих:",
            google_source,
        )

        google_form.addRow(
            "Перевод входящих:",
            google_target,
        )

        self.google_source_language = google_source
        self.google_target_language = google_target

        google_layout.addWidget(
            google_group,
        )

        google_info = QLabel(
            "Google Translate не требует API key. "
            "Для исходящих сообщений направление переворачивается автоматически."
        )

        google_info.setWordWrap(
            True,
        )

        google_layout.addWidget(
            google_info,
        )

        google_reset = QPushButton(
            "Сбросить настройки Google Translate",
        )

        google_reset.clicked.connect(
            lambda: self._reset_provider("google"),
        )

        google_layout.addWidget(
            google_reset,
        )

        google_layout.addStretch()

        self.provider_pages["google"] = google_page

        self.provider_stack.addTab(
            google_page,
            "Google Translate",
        )

        # ----------------------------------------------------
        # AI providers
        # ----------------------------------------------------

        for provider_id, title in (
            ("gemini", "Gemini"),
            ("openrouter", "OpenRouter"),
        ):
            page = self._build_ai_provider_page(
                provider_id=provider_id,
                title=title,
                host=False,
            )

            self.provider_pages[provider_id] = page

            self.provider_stack.addTab(
                page,
                title,
            )

        # ----------------------------------------------------
        # Ollama
        # ----------------------------------------------------

        ollama_page = self._build_ai_provider_page(
            provider_id="ollama",
            title="Ollama",
            host=True,
        )

        self.provider_pages["ollama"] = ollama_page

        self.provider_stack.addTab(
            ollama_page,
            "Ollama",
        )

        # ----------------------------------------------------
        # Список
        # ----------------------------------------------------

        for provider_id, name in PROVIDER_NAMES.items():
            item = QListWidgetItem(
                name,
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                provider_id,
            )

            self.provider_list.addItem(
                item,
            )

    # ========================================================
    # AI provider page
    # ========================================================

    def _build_ai_provider_page(
        self,
        provider_id: str,
        title: str,
        host: bool = False,
    ) -> QWidget:

        page = QWidget()

        layout = QVBoxLayout(
            page,
        )

        group = QGroupBox(
            title,
        )

        form = QFormLayout(
            group,
        )

        # ----------------------------------------------------
        # Состояние
        # ----------------------------------------------------

        enabled = QComboBox()

        enabled.addItem(
            "Выключен",
            False,
        )

        enabled.addItem(
            "Включен",
            True,
        )

        form.addRow(
            "Состояние:",
            enabled,
        )

        setattr(
            self,
            f"{provider_id}_enabled",
            enabled,
        )

        # ----------------------------------------------------
        # API key
        # ----------------------------------------------------

        if not host:
            api_key = QLineEdit()

            api_key.setEchoMode(
                QLineEdit.EchoMode.Password,
            )

            form.addRow(
                "API key:",
                api_key,
            )

            setattr(
                self,
                f"{provider_id}_api_key",
                api_key,
            )

        # ----------------------------------------------------
        # Host
        # ----------------------------------------------------

        if host:
            host_edit = QLineEdit()

            form.addRow(
                "Host:",
                host_edit,
            )

            setattr(
                self,
                f"{provider_id}_host",
                host_edit,
            )

        # ----------------------------------------------------
        # Model
        # ----------------------------------------------------

        model = QLineEdit()

        form.addRow(
            "Модель:",
            model,
        )

        setattr(
            self,
            f"{provider_id}_model",
            model,
        )

        # ----------------------------------------------------
        # Languages
        # ----------------------------------------------------

        source_language = QLineEdit()

        form.addRow(
            "Язык входящих:",
            source_language,
        )

        setattr(
            self,
            f"{provider_id}_source_language",
            source_language,
        )

        target_language = QLineEdit()

        form.addRow(
            "Перевод входящих:",
            target_language,
        )

        setattr(
            self,
            f"{provider_id}_target_language",
            target_language,
        )

        # ----------------------------------------------------
        # System prompt
        # ----------------------------------------------------

        prompt = QPlainTextEdit()

        prompt.setMinimumHeight(
            180,
        )

        form.addRow(
            "System prompt:",
            prompt,
        )

        setattr(
            self,
            f"{provider_id}_system_prompt",
            prompt,
        )

        layout.addWidget(
            group,
        )

        direction_info = QLabel(
            "Для исходящих сообщений направление переворачивается автоматически."
        )

        direction_info.setWordWrap(
            True,
        )

        layout.addWidget(
            direction_info,
        )

        reset_button = QPushButton(
            f"Сбросить настройки {title}",
        )

        reset_button.clicked.connect(
            lambda: self._reset_provider(provider_id),
        )

        layout.addWidget(
            reset_button,
        )

        layout.addStretch()

        return page

    # ========================================================
    # Маршрутизация
    # ========================================================

    def _build_routing_tab(self):

        tab = QWidget()

        layout = QHBoxLayout(tab)

        self.routing_channel_list = QListWidget()
        self.routing_provider_list = QListWidget()

        self.routing_channel_list.currentItemChanged.connect(
            self._routing_channel_selected,
        )

        layout.addWidget(
            self.routing_channel_list,
            1,
        )

        layout.addWidget(
            self.routing_provider_list,
            2,
        )

        self.routing_provider_list.itemDoubleClicked.connect(
            self._routing_provider_double_clicked,
        )

        for channel_id, title in ROUTING_CHANNELS:
            item = QListWidgetItem(
                title,
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                channel_id,
            )

            self.routing_channel_list.addItem(
                item,
            )

        self._rebuild_routing_provider_list()

        self.tabs.addTab(
            tab,
            "Маршрутизация",
        )

    # ========================================================
    # Загрузка настроек
    # ========================================================

    def _load_all_settings(self):

        self._load_general_settings()
        self._load_overlay_settings()
        self._load_provider_settings()
        self._load_routing_settings()

    # --------------------------------------------------------

    def _load_general_settings(self):

        self.log_path_edit.setText(
            config.log_path,
        )

        point = config.game_chat_input_point

        self.game_chat_x.setValue(
            point["x"],
        )

        self.game_chat_y.setValue(
            point["y"],
        )

        if config.game_chat_input_point_configured:
            self.calibration_status.setText(
                f"Точка настроена: ({point['x']}, {point['y']})"
            )
        else:
            self.calibration_status.setText(
                "Точка не настроена.",
            )

    # --------------------------------------------------------

    def _load_overlay_settings(self):

        geometry = config.overlay_geometry

        self.overlay_x.setValue(
            int(geometry.get("x", 0)),
        )

        self.overlay_y.setValue(
            int(geometry.get("y", 0)),
        )

        self.overlay_width.setValue(
            int(geometry.get("w", 700)),
        )

        self.overlay_height.setValue(
            int(geometry.get("h", 300)),
        )

        self.font_size.setValue(
            config.font_size,
        )

        outgoing_channel = config.get(
            "overlay",
            "outgoing_channel",
            default="local",
        )

        index = self.outgoing_channel.findData(
            outgoing_channel,
        )

        if index >= 0:
            self.outgoing_channel.setCurrentIndex(
                index,
            )

    # --------------------------------------------------------

    def _load_provider_settings(self):

        for provider_id in PROVIDER_NAMES:
            provider = config.get(
                "providers",
                provider_id,
                default={},
            ) or {}

            enabled = getattr(
                self,
                f"{provider_id}_enabled",
                None,
            )

            if enabled is not None:
                index = enabled.findData(
                    bool(provider.get("enabled", False)),
                )

                if index >= 0:
                    enabled.setCurrentIndex(
                        index,
                    )

            source = getattr(
                self,
                f"{provider_id}_source_language",
                None,
            )

            if source is not None:
                source.setText(
                    str(provider.get("source_language", "en")),
                )

            target = getattr(
                self,
                f"{provider_id}_target_language",
                None,
            )

            if target is not None:
                target.setText(
                    str(provider.get("target_language", "ru")),
                )

            model = getattr(
                self,
                f"{provider_id}_model",
                None,
            )

            if model is not None:
                model.setText(
                    str(provider.get("model", "")),
                )

            prompt = getattr(
                self,
                f"{provider_id}_system_prompt",
                None,
            )

            if prompt is not None:
                prompt.setPlainText(
                    str(provider.get("system_prompt", "")),
                )

            host = getattr(
                self,
                f"{provider_id}_host",
                None,
            )

            if host is not None:
                host.setText(
                    str(provider.get("host", "http://127.0.0.1:11434")),
                )

            api_key = getattr(
                self,
                f"{provider_id}_api_key",
                None,
            )

            if api_key is not None:
                api_key.setText(
                    config.provider_api_key(provider_id),
                )

        self.current_provider_id = "google"

        if self.provider_list.count() > 0:
            self.provider_list.setCurrentRow(0)

    # --------------------------------------------------------

    def _load_routing_settings(self):

        self.routing_data = deepcopy(
            config.all_routes(),
        )

        if self.routing_channel_list.count() > 0:
            self.routing_channel_list.setCurrentRow(0)

    # ========================================================
    # События провайдеров
    # ========================================================

    def _provider_selected(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ):

        if current is None:
            return

        provider_id = current.data(
            Qt.ItemDataRole.UserRole,
        )

        self.current_provider_id = provider_id

        index = self.provider_stack.indexOf(
            self.provider_pages.get(provider_id),
        )

        if index >= 0:
            self.provider_stack.setCurrentIndex(
                index,
            )

    # ========================================================
    # События маршрутизации
    # ========================================================

    def _routing_channel_selected(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ):

        if current is None:
            return

        channel_id = current.data(
            Qt.ItemDataRole.UserRole,
        )

        self.current_routing_channel = channel_id

        self._rebuild_routing_provider_list()

    # --------------------------------------------------------

    def _rebuild_routing_provider_list(self):

        self.routing_provider_list.clear()

        if self.current_routing_channel is None:
            return

        route = self.routing_data.get(
            self.current_routing_channel,
            [],
        )

        for provider_id in AI_PROVIDERS:
            name = PROVIDER_NAMES.get(
                provider_id,
                provider_id,
            )

            item = QListWidgetItem(
                name,
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                provider_id,
            )

            item.setCheckState(
                Qt.CheckState.Checked
                if provider_id in route
                else Qt.CheckState.Unchecked
            )

            self.routing_provider_list.addItem(
                item,
            )

    # --------------------------------------------------------

    def _routing_provider_double_clicked(
        self,
        item: QListWidgetItem,
    ):

        checked = item.checkState() == Qt.CheckState.Checked

        item.setCheckState(
            Qt.CheckState.Unchecked
            if checked
            else Qt.CheckState.Checked
        )

        self._update_current_route()

    # --------------------------------------------------------

    def _update_current_route(self):

        if self.current_routing_channel is None:
            return

        route = []

        for index in range(
            self.routing_provider_list.count(),
        ):
            item = self.routing_provider_list.item(
                index,
            )

            if item.checkState() == Qt.CheckState.Checked:
                route.append(
                    item.data(
                        Qt.ItemDataRole.UserRole,
                    )
                )

        self.routing_data[self.current_routing_channel] = route

    # ========================================================
    # Обзор файла
    # ========================================================

    def _browse_log_file(self):

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите LatestClient.txt",
            "",
            "Text files (*.txt);;All files (*.*)",
        )

        if filename:
            self.log_path_edit.setText(
                filename,
            )

    # ========================================================
    # Сброс провайдера
    # ========================================================

    def _reset_provider(
        self,
        provider_id: str,
    ):

        answer = QMessageBox.question(
            self,
            "Сброс настроек",
            f"Сбросить настройки провайдера {PROVIDER_NAMES.get(provider_id, provider_id)}?",
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        config.reset_provider(
            provider_id,
        )

        self._load_provider_settings()

    # ========================================================
    # Сохранение
    # ========================================================

    def _save_and_accept(self):

        config.log_path = self.log_path_edit.text().strip()

        config.set_game_chat_input_point(
            self.game_chat_x.value(),
            self.game_chat_y.value(),
        )

        config.overlay_geometry = {
            "x": self.overlay_x.value(),
            "y": self.overlay_y.value(),
            "w": self.overlay_width.value(),
            "h": self.overlay_height.value(),
        }

        config.font_size = self.font_size.value()

        config.set(
            "overlay",
            "outgoing_channel",
            value=self.outgoing_channel.currentData(),
        )

        self._update_current_route()

        for channel_id, route in self.routing_data.items():
            config.set_route(
                channel_id,
                route,
            )

        for provider_id in PROVIDER_NAMES:
            provider = config.get(
                "providers",
                provider_id,
                default={},
            ) or {}

            enabled = getattr(
                self,
                f"{provider_id}_enabled",
                None,
            )

            if enabled is not None:
                provider["enabled"] = bool(
                    enabled.currentData()
                )

            source = getattr(
                self,
                f"{provider_id}_source_language",
                None,
            )

            if source is not None:
                provider["source_language"] = source.text().strip() or "en"

            target = getattr(
                self,
                f"{provider_id}_target_language",
                None,
            )

            if target is not None:
                provider["target_language"] = target.text().strip() or "ru"

            model = getattr(
                self,
                f"{provider_id}_model",
                None,
            )

            if model is not None:
                provider["model"] = model.text().strip()

            prompt = getattr(
                self,
                f"{provider_id}_system_prompt",
                None,
            )

            if prompt is not None:
                provider["system_prompt"] = prompt.toPlainText().strip()

            host = getattr(
                self,
                f"{provider_id}_host",
                None,
            )

            if host is not None:
                provider["host"] = host.text().strip()

            api_key = getattr(
                self,
                f"{provider_id}_api_key",
                None,
            )

            if api_key is not None:
                config.set_provider_api_key(
                    provider_id,
                    api_key.text().strip(),
                )

            config.set(
                "providers",
                provider_id,
                value=provider,
            )

        config.save()

        self.accept()
