from __future__ import annotations

from copy import deepcopy
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
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
    ("global", "Global — Глобальный"),
    ("local", "Local — Область"),
    ("trade", "Trade — Торговый"),
    ("party", "Party — Группа"),
    ("guild", "Guild — Гильдия"),
    ("whisper", "Whisper — Личные сообщения"),
]


# ============================================================
# Провайдеры
# ============================================================

PROVIDER_NAMES = {
    "google": "Google Translate",
    "gemini": "Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "ollama": "Ollama",
}


AI_PROVIDERS = (
    "gemini",
    "groq",
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

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Exilingo — Настройки")
        self.setMinimumSize(820, 650)

        self.registry = ProviderRegistry()

        self.current_provider_id: Optional[str] = None
        self.current_routing_channel: Optional[str] = None

        self.routing_data: Dict[str, List[str]] = {}

        # ----------------------------------------------------
        # Основной layout
        # ----------------------------------------------------

        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

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

        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)

        main_layout.addWidget(buttons)

        # ----------------------------------------------------
        # Загрузка настроек
        # ----------------------------------------------------

        self._load_all_settings()

    # ========================================================
    # Общие
    # ========================================================

    def _build_general_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ----------------------------------------------------
        # Path of Exile
        # ----------------------------------------------------

        group = QGroupBox("Path of Exile")
        form = QFormLayout(group)

        self.log_path_edit = QLineEdit()

        self.log_path_edit.setPlaceholderText(
            r"C:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt"
        )

        browse_button = QPushButton("Обзор...")
        browse_button.clicked.connect(self._browse_log_file)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.log_path_edit)
        path_layout.addWidget(browse_button)

        form.addRow(
            "LatestClient.txt:",
            path_layout,
        )

        layout.addWidget(group)

        # ----------------------------------------------------
        # Информация
        # ----------------------------------------------------

        info = QLabel(
            "Путь к LatestClient.txt является обязательным "
            "для получения сообщений игрового чата."
        )

        info.setWordWrap(True)

        layout.addWidget(info)
        layout.addStretch()

        self.tabs.addTab(
            tab,
            "Общие",
        )

    # ========================================================
    # Overlay
    # ========================================================

    def _build_overlay_tab(self):

        tab = QWidget()
        layout = QVBoxLayout(tab)

        # ----------------------------------------------------
        # Геометрия
        # ----------------------------------------------------

        geometry_group = QGroupBox("Размер и положение")
        geometry_form = QFormLayout(geometry_group)

        self.overlay_x = QSpinBox()
        self.overlay_x.setRange(-10000, 10000)

        self.overlay_y = QSpinBox()
        self.overlay_y.setRange(-10000, 10000)

        self.overlay_width = QSpinBox()
        self.overlay_width.setRange(100, 10000)

        self.overlay_height = QSpinBox()
        self.overlay_height.setRange(50, 10000)

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

        layout.addWidget(geometry_group)

        # ----------------------------------------------------
        # Шрифт
        # ----------------------------------------------------

        font_group = QGroupBox("Текст")
        font_form = QFormLayout(font_group)

        self.overlay_font_size = QSpinBox()
        self.overlay_font_size.setRange(6, 72)

        font_form.addRow(
            "Размер шрифта:",
            self.overlay_font_size,
        )

        layout.addWidget(font_group)

        # ----------------------------------------------------
        # Информация
        # ----------------------------------------------------

        info = QLabel(
            "Эти параметры определяют положение, размер и "
            "размер текста игрового чата в оверлее."
        )

        info.setWordWrap(True)

        layout.addWidget(info)
        layout.addStretch()

        self.tabs.addTab(
            tab,
            "Overlay",
        )

    # ========================================================
    # Переводчики
    # ========================================================

    def _build_providers_tab(self):

        tab = QWidget()
        main_layout = QHBoxLayout(tab)

        # ----------------------------------------------------
        # Список
        # ----------------------------------------------------

        left_layout = QVBoxLayout()

        left_layout.addWidget(QLabel("Доступные переводчики:"))

        self.provider_list = QListWidget()

        self.provider_list.currentItemChanged.connect(self._provider_selection_changed)

        left_layout.addWidget(self.provider_list)

        main_layout.addLayout(
            left_layout,
            1,
        )

        # ----------------------------------------------------
        # Настройки
        # ----------------------------------------------------

        right_layout = QVBoxLayout()

        self.provider_stack = QTabWidget()

        right_layout.addWidget(self.provider_stack)

        main_layout.addLayout(
            right_layout,
            3,
        )

        self._build_provider_pages()

        self.tabs.addTab(
            tab,
            "Переводчики",
        )

    # ========================================================
    # Страницы провайдеров
    # ========================================================

    def _build_provider_pages(self):

        self.provider_pages: Dict[str, QWidget] = {}

        # ----------------------------------------------------
        # Google
        # ----------------------------------------------------

        google_page = QWidget()
        google_layout = QVBoxLayout(google_page)

        google_group = QGroupBox("Google Translate")

        google_form = QFormLayout(google_group)

        self.google_enabled = QCheckBox()
        self.google_enabled.setChecked(True)

        google_form.addRow(
            "Активен:",
            self.google_enabled,
        )

        self.google_source = QLineEdit()

        google_form.addRow(
            "Исходный язык:",
            self.google_source,
        )

        self.google_target = QLineEdit()

        google_form.addRow(
            "Целевой язык:",
            self.google_target,
        )

        google_layout.addWidget(google_group)

        google_reset = QPushButton("Восстановить настройки по умолчанию")

        google_reset.clicked.connect(lambda: self._reset_provider("google"))

        google_layout.addWidget(google_reset)

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
            ("groq", "Groq"),
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
        # Список провайдеров
        # ----------------------------------------------------

        for provider_id, name in PROVIDER_NAMES.items():
            item = QListWidgetItem(name)

            item.setData(
                Qt.ItemDataRole.UserRole,
                provider_id,
            )

            self.provider_list.addItem(item)

    # ========================================================
    # Страница AI-провайдера
    # ========================================================

    def _build_ai_provider_page(
        self,
        provider_id: str,
        title: str,
        host: bool = False,
    ) -> QWidget:

        page = QWidget()
        layout = QVBoxLayout(page)

        group = QGroupBox(title)
        form = QFormLayout(group)

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

            api_key.setEchoMode(QLineEdit.EchoMode.Password)

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
        # System prompt
        # ----------------------------------------------------

        prompt = QPlainTextEdit()

        prompt.setMinimumHeight(180)

        form.addRow(
            "System prompt:",
            prompt,
        )

        setattr(
            self,
            f"{provider_id}_system_prompt",
            prompt,
        )

        layout.addWidget(group)

        # ----------------------------------------------------
        # Reset
        # ----------------------------------------------------

        reset_button = QPushButton("Восстановить настройки по умолчанию")

        reset_button.clicked.connect(lambda: self._reset_provider(provider_id))

        layout.addWidget(reset_button)

        layout.addStretch()

        return page

    # ========================================================
    # Provider selection
    # ========================================================

    def _provider_selection_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ):

        if current is None:
            return

        provider_id = current.data(Qt.ItemDataRole.UserRole)

        self.current_provider_id = provider_id

        page = self.provider_pages.get(provider_id)

        if page is None:
            return

        index = self.provider_stack.indexOf(page)

        if index >= 0:
            self.provider_stack.setCurrentIndex(index)

    # ========================================================
    # Маршрутизация
    # ========================================================

    def _build_routing_tab(self):

        tab = QWidget()
        main_layout = QHBoxLayout(tab)

        # ----------------------------------------------------
        # Каналы
        # ----------------------------------------------------

        left_layout = QVBoxLayout()

        left_layout.addWidget(QLabel("Канал:"))

        self.routing_channel_list = QListWidget()

        self.routing_channel_list.currentItemChanged.connect(
            self._routing_channel_changed
        )

        left_layout.addWidget(self.routing_channel_list)

        main_layout.addLayout(
            left_layout,
            1,
        )

        # ----------------------------------------------------
        # Очередь
        # ----------------------------------------------------

        right_layout = QVBoxLayout()

        right_layout.addWidget(
            QLabel("Очередь переводчиков (сверху — высший приоритет):")
        )

        self.routing_queue = QListWidget()

        right_layout.addWidget(self.routing_queue)

        # ----------------------------------------------------
        # Кнопки
        # ----------------------------------------------------

        buttons_layout = QHBoxLayout()

        self.routing_add_button = QPushButton("+")
        self.routing_remove_button = QPushButton("-")
        self.routing_up_button = QPushButton("↑")
        self.routing_down_button = QPushButton("↓")

        self.routing_add_button.setToolTip("Добавить доступного переводчика")

        self.routing_remove_button.setToolTip("Удалить выбранного переводчика")

        self.routing_up_button.setToolTip("Повысить приоритет")

        self.routing_down_button.setToolTip("Понизить приоритет")

        buttons_layout.addWidget(self.routing_add_button)

        buttons_layout.addWidget(self.routing_remove_button)

        buttons_layout.addWidget(self.routing_up_button)

        buttons_layout.addWidget(self.routing_down_button)

        right_layout.addLayout(buttons_layout)

        main_layout.addLayout(
            right_layout,
            2,
        )

        # ----------------------------------------------------
        # Сигналы
        # ----------------------------------------------------

        self.routing_add_button.clicked.connect(self._routing_add_provider)

        self.routing_remove_button.clicked.connect(self._routing_remove_provider)

        self.routing_up_button.clicked.connect(self._routing_move_up)

        self.routing_down_button.clicked.connect(self._routing_move_down)

        # ----------------------------------------------------
        # Каналы
        # ----------------------------------------------------

        for channel_id, channel_name in ROUTING_CHANNELS:
            item = QListWidgetItem(channel_name)

            item.setData(
                Qt.ItemDataRole.UserRole,
                channel_id,
            )

            self.routing_channel_list.addItem(item)

        self.tabs.addTab(
            tab,
            "Маршрутизация",
        )

    # ========================================================
    # Смена канала
    # ========================================================

    def _routing_channel_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ):

        # ----------------------------------------------------
        # Сохраняем предыдущий канал в памяти GUI
        # ----------------------------------------------------

        if previous is not None:
            previous_channel = previous.data(Qt.ItemDataRole.UserRole)

            self.routing_data[previous_channel] = self._get_current_routing_queue()

        if current is None:
            return

        # ----------------------------------------------------
        # Новый канал
        # ----------------------------------------------------

        channel = current.data(Qt.ItemDataRole.UserRole)

        self.current_routing_channel = channel

        queue = self.routing_data.get(
            channel,
            ["google"],
        )

        self._display_routing_queue(queue)

    # ========================================================
    # Получить текущую очередь
    # ========================================================

    def _get_current_routing_queue(
        self,
    ) -> List[str]:

        result = []

        for index in range(self.routing_queue.count()):
            item = self.routing_queue.item(index)

            provider_id = item.data(Qt.ItemDataRole.UserRole)

            if provider_id:
                result.append(provider_id)

        return result

    # ========================================================
    # Отобразить очередь
    # ========================================================

    def _display_routing_queue(
        self,
        providers: List[str],
    ):

        self.routing_queue.clear()

        available = set(self._available_provider_ids())

        # Сохраняем только доступные
        # и не дублируем провайдеров.

        seen = set()

        for provider_id in providers:
            if provider_id in seen:
                continue

            if provider_id not in available:
                continue

            seen.add(provider_id)

            self._add_queue_item(provider_id)

        # Если после фильтрации очередь
        # оказалась пустой — Google.

        if self.routing_queue.count() == 0:
            self._add_queue_item("google")

    # ========================================================
    # Добавить элемент очереди
    # ========================================================

    def _add_queue_item(
        self,
        provider_id: str,
    ):

        item = QListWidgetItem(
            PROVIDER_NAMES.get(
                provider_id,
                provider_id,
            )
        )

        item.setData(
            Qt.ItemDataRole.UserRole,
            provider_id,
        )

        self.routing_queue.addItem(item)

    # ========================================================
    # Добавить провайдера
    # ========================================================

    def _routing_add_provider(self):

        if self.current_routing_channel is None:
            return

        existing = set(self._get_current_routing_queue())

        for provider_id in self._available_provider_ids():
            if provider_id in existing:
                continue

            self._add_queue_item(provider_id)

            self.routing_queue.setCurrentRow(self.routing_queue.count() - 1)

            break

    # ========================================================
    # Удалить провайдера
    # ========================================================

    def _routing_remove_provider(self):

        row = self.routing_queue.currentRow()

        if row < 0:
            return

        # Google должен оставаться
        # доступным fallback.

        item = self.routing_queue.item(row)

        provider_id = item.data(Qt.ItemDataRole.UserRole)

        if provider_id == "google" and self.routing_queue.count() == 1:
            return

        self.routing_queue.takeItem(row)

    # ========================================================
    # Переместить вверх
    # ========================================================

    def _routing_move_up(self):

        row = self.routing_queue.currentRow()

        if row <= 0:
            return

        item = self.routing_queue.takeItem(row)

        self.routing_queue.insertItem(
            row - 1,
            item,
        )

        self.routing_queue.setCurrentRow(row - 1)

    # ========================================================
    # Переместить вниз
    # ========================================================

    def _routing_move_down(self):

        row = self.routing_queue.currentRow()

        if row < 0:
            return

        if row >= self.routing_queue.count() - 1:
            return

        item = self.routing_queue.takeItem(row)

        self.routing_queue.insertItem(
            row + 1,
            item,
        )

        self.routing_queue.setCurrentRow(row + 1)

    # ========================================================
    # Проверка доступности провайдера
    # ========================================================

    def _provider_is_available(
        self,
        provider_id: str,
    ) -> bool:

        # ----------------------------------------------------
        # Google доступен по умолчанию.
        # ----------------------------------------------------

        if provider_id == "google":
            return self.google_enabled.isChecked()

        # ----------------------------------------------------
        # Остальные провайдеры
        # ----------------------------------------------------

        if provider_id not in AI_PROVIDERS:
            return False

        enabled_widget = getattr(
            self,
            f"{provider_id}_enabled",
            None,
        )

        if enabled_widget is None:
            return False

        if enabled_widget.currentData() is not True:
            return False

        # ----------------------------------------------------
        # Ollama
        # ----------------------------------------------------

        if provider_id == "ollama":
            host_widget = getattr(
                self,
                "ollama_host",
                None,
            )

            model_widget = getattr(
                self,
                "ollama_model",
                None,
            )

            if host_widget is None:
                return False

            if model_widget is None:
                return False

            if not host_widget.text().strip():
                return False

            if not model_widget.text().strip():
                return False

            return True

        # ----------------------------------------------------
        # API providers
        # ----------------------------------------------------

        api_widget = getattr(
            self,
            f"{provider_id}_api_key",
            None,
        )

        model_widget = getattr(
            self,
            f"{provider_id}_model",
            None,
        )

        if api_widget is None:
            return False

        if model_widget is None:
            return False

        if not api_widget.text().strip():
            return False

        if not model_widget.text().strip():
            return False

        return True

    # ========================================================
    # Список доступных провайдеров
    # ========================================================

    def _available_provider_ids(
        self,
    ) -> List[str]:

        result = []

        for provider_id in PROVIDER_NAMES:
            if self._provider_is_available(provider_id):
                result.append(provider_id)

        return result

    # ========================================================
    # Загрузка всех настроек
    # ========================================================

    def _load_all_settings(self):

        # ----------------------------------------------------
        # General
        # ----------------------------------------------------

        self.log_path_edit.setText(config.log_path)

        # ----------------------------------------------------
        # Overlay
        # ----------------------------------------------------

        geometry = config.overlay_geometry or {}

        self.overlay_x.setValue(int(geometry.get("x", 1)))

        self.overlay_y.setValue(int(geometry.get("y", 11)))

        self.overlay_width.setValue(int(geometry.get("w", 700)))

        self.overlay_height.setValue(int(geometry.get("h", 309)))

        self.overlay_font_size.setValue(int(config.font_size))

        # ----------------------------------------------------
        # Google
        # ----------------------------------------------------

        google = config.get_provider("google")

        self.google_enabled.setChecked(
            google.get(
                "enabled",
                True,
            )
        )

        self.google_source.setText(
            google.get(
                "source_language",
                "en",
            )
        )

        self.google_target.setText(
            google.get(
                "target_language",
                "ru",
            )
        )

        # ----------------------------------------------------
        # AI providers
        # ----------------------------------------------------

        for provider_id in AI_PROVIDERS:
            data = config.get_provider(provider_id)

            enabled_widget = getattr(
                self,
                f"{provider_id}_enabled",
            )

            enabled_widget.setCurrentIndex(
                1
                if data.get(
                    "enabled",
                    False,
                )
                else 0
            )

            model_widget = getattr(
                self,
                f"{provider_id}_model",
            )

            model_widget.setText(
                data.get(
                    "model",
                    "",
                )
            )

            prompt_widget = getattr(
                self,
                f"{provider_id}_system_prompt",
            )

            prompt_widget.setPlainText(
                data.get(
                    "system_prompt",
                    "",
                )
            )

            if provider_id == "ollama":
                host_widget = getattr(
                    self,
                    "ollama_host",
                )

                host_widget.setText(
                    data.get(
                        "host",
                        "http://127.0.0.1:11434",
                    )
                )

            else:
                api_widget = getattr(
                    self,
                    f"{provider_id}_api_key",
                )

                api_widget.setText(
                    data.get(
                        "api_key",
                        "",
                    )
                )

        # ----------------------------------------------------
        # Routing
        # ----------------------------------------------------

        self.routing_data = {}

        for channel_id, _ in ROUTING_CHANNELS:
            route = config.route(channel_id)

            if not route:
                route = ["google"]

            self.routing_data[channel_id] = list(route)

        if self.routing_channel_list.count():
            self.routing_channel_list.setCurrentRow(0)

            first = self.routing_channel_list.item(0)

            self._routing_channel_changed(
                first,
                None,
            )

        # ----------------------------------------------------
        # Providers list
        # ----------------------------------------------------

        if self.provider_list.count():
            self.provider_list.setCurrentRow(0)

    # ========================================================
    # Сохранение всех настроек
    # ========================================================

    def _save_all_settings(self):

        # ----------------------------------------------------
        # General
        # ----------------------------------------------------

        log_path = self.log_path_edit.text().strip()

        config.log_path = log_path

        # ----------------------------------------------------
        # Overlay
        # ----------------------------------------------------

        config.overlay_geometry = {
            "x": self.overlay_x.value(),
            "y": self.overlay_y.value(),
            "w": self.overlay_width.value(),
            "h": self.overlay_height.value(),
        }

        config.font_size = self.overlay_font_size.value()

        # ----------------------------------------------------
        # Google
        # ----------------------------------------------------

        config.set(
            "providers",
            "google",
            value={
                "enabled": self.google_enabled.isChecked(),
                "source_language": (self.google_source.text().strip() or "en"),
                "target_language": (self.google_target.text().strip() or "ru"),
            },
        )

        # ----------------------------------------------------
        # AI providers
        # ----------------------------------------------------

        for provider_id in AI_PROVIDERS:
            data = deepcopy(config.get_provider(provider_id))

            data["enabled"] = (
                getattr(
                    self,
                    f"{provider_id}_enabled",
                ).currentData()
                is True
            )

            data["model"] = (
                getattr(
                    self,
                    f"{provider_id}_model",
                )
                .text()
                .strip()
            )

            data["system_prompt"] = (
                getattr(
                    self,
                    f"{provider_id}_system_prompt",
                )
                .toPlainText()
                .strip()
            )

            if provider_id == "ollama":
                data["host"] = self.ollama_host.text().strip()

            else:
                data["api_key"] = (
                    getattr(
                        self,
                        f"{provider_id}_api_key",
                    )
                    .text()
                    .strip()
                )

            config.set(
                "providers",
                provider_id,
                value=data,
            )

        # ----------------------------------------------------
        # Сохраняем последний открытый канал
        # ----------------------------------------------------

        if self.current_routing_channel is not None:
            self.routing_data[self.current_routing_channel] = (
                self._get_current_routing_queue()
            )

        # ----------------------------------------------------
        # Routing
        # ----------------------------------------------------

        for channel_id, _ in ROUTING_CHANNELS:
            queue = list(
                self.routing_data.get(
                    channel_id,
                    ["google"],
                )
            )

            # Удаляем неактивных провайдеров.
            queue = [
                provider_id
                for provider_id in queue
                if self._provider_is_available(provider_id)
            ]

            # Удаляем дубли.
            unique_queue = []

            for provider_id in queue:
                if provider_id not in unique_queue:
                    unique_queue.append(provider_id)

            queue = unique_queue

            # Google — обязательный fallback.
            if not queue:
                queue = ["google"]

            config.set(
                "routing",
                channel_id,
                value=queue,
            )

    # ========================================================
    # Сохранить и закрыть
    # ========================================================

    def _save_and_accept(self):

        try:
            self._save_all_settings()

            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Ошибка сохранения",
                str(e),
            )

    # ========================================================
    # Выбор LatestClient.txt
    # ========================================================

    def _browse_log_file(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите LatestClient.txt",
            "",
            "Text files (*.txt);;All files (*.*)",
        )

        if path:
            self.log_path_edit.setText(path)

    # ========================================================
    # Восстановление настроек провайдера
    # ========================================================

    def _reset_provider(
        self,
        provider_id: str,
    ):

        answer = QMessageBox.question(
            self,
            "Восстановить настройки",
            (
                "Восстановить настройки "
                f"{PROVIDER_NAMES.get(provider_id, provider_id)} "
                "по умолчанию?"
            ),
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        defaults = DEFAULT_CONFIG["providers"].get(
            provider_id,
            {},
        )

        # ----------------------------------------------------
        # Google
        # ----------------------------------------------------

        if provider_id == "google":
            self.google_enabled.setChecked(
                defaults.get(
                    "enabled",
                    True,
                )
            )

            self.google_source.setText(
                defaults.get(
                    "source_language",
                    "en",
                )
            )

            self.google_target.setText(
                defaults.get(
                    "target_language",
                    "ru",
                )
            )

            return

        # ----------------------------------------------------
        # AI provider
        # ----------------------------------------------------

        enabled_widget = getattr(
            self,
            f"{provider_id}_enabled",
        )

        enabled_widget.setCurrentIndex(
            1
            if defaults.get(
                "enabled",
                False,
            )
            else 0
        )

        model_widget = getattr(
            self,
            f"{provider_id}_model",
        )

        model_widget.setText(
            defaults.get(
                "model",
                "",
            )
        )

        prompt_widget = getattr(
            self,
            f"{provider_id}_system_prompt",
        )

        prompt_widget.setPlainText(
            defaults.get(
                "system_prompt",
                "",
            )
        )

        if provider_id == "ollama":
            self.ollama_host.setText(
                defaults.get(
                    "host",
                    "http://127.0.0.1:11434",
                )
            )

        else:
            api_widget = getattr(
                self,
                f"{provider_id}_api_key",
            )

            api_widget.setText(
                defaults.get(
                    "api_key",
                    "",
                )
            )

    # ========================================================
    # Открыть настройки
    # ========================================================

    @staticmethod
    def open_settings(
        parent: Optional[QWidget] = None,
    ) -> bool:

        dialog = SettingsDialog(parent)

        return dialog.exec() == QDialog.DialogCode.Accepted


# ============================================================
# Standalone test
# ============================================================

if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)

    dialog = SettingsDialog()

    dialog.show()

    sys.exit(app.exec())
