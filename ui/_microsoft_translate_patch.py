from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.config_manager import DEFAULT_CONFIG, config
from core.microsoft_translate_patch import (
    MICROSOFT_DEFAULT_ENDPOINT,
    MICROSOFT_PROVIDER_ID,
    MicrosoftTranslateTranslator,
)

from . import _settings_dialog_patch as settings_patch
from .settings_dialog import PROVIDER_NAMES, SettingsDialog


MICROSOFT_PROVIDER_NAME = "Microsoft Translator"
PROVIDER_NAMES[MICROSOFT_PROVIDER_ID] = MICROSOFT_PROVIDER_NAME

_original_provider_pages = SettingsDialog._build_provider_pages
_original_provider_is_available = SettingsDialog._provider_is_available
_original_load_all_settings = SettingsDialog._load_all_settings
_original_save_all_settings = SettingsDialog._save_all_settings
_original_reset_provider = SettingsDialog._reset_provider


def _build_microsoft_page(dialog: SettingsDialog) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)

    group = QGroupBox(MICROSOFT_PROVIDER_NAME)
    form = QFormLayout(group)

    enabled = QComboBox()
    enabled.addItem("Выключен", False)
    enabled.addItem("Включен", True)
    form.addRow("Состояние:", enabled)
    dialog.microsoft_enabled = enabled

    api_key = QLineEdit()
    api_key.setEchoMode(QLineEdit.EchoMode.Password)
    form.addRow("API key:", api_key)
    dialog.microsoft_api_key = api_key

    source = QLineEdit()
    form.addRow("Язык входящих:", source)
    dialog.microsoft_source_language = source

    target = QLineEdit()
    form.addRow("Перевод входящих:", target)
    dialog.microsoft_target_language = target

    endpoint = QLineEdit()
    form.addRow("Endpoint:", endpoint)
    dialog.microsoft_endpoint = endpoint

    region = QLineEdit()
    region.setPlaceholderText("Не требуется для Global Translator Resource")
    form.addRow("Region:", region)
    dialog.microsoft_region = region

    layout.addWidget(group)

    info = QLabel(
        "Microsoft Translator использует официальный Azure Translator API. "
        "Для исходящих сообщений направление переворачивается автоматически. "
        "Для Global Translator Resource поле Region можно оставить пустым."
    )
    info.setWordWrap(True)
    layout.addWidget(info)

    reset_button = QPushButton("Восстановить настройки по умолчанию")
    reset_button.clicked.connect(lambda: dialog._reset_provider(MICROSOFT_PROVIDER_ID))
    layout.addWidget(reset_button)
    layout.addStretch()
    return page


def _patched_build_provider_pages(self: SettingsDialog):
    _original_provider_pages(self)
    page = _build_microsoft_page(self)
    self.provider_pages[MICROSOFT_PROVIDER_ID] = page
    self.provider_stack.addTab(page, MICROSOFT_PROVIDER_NAME)

    item = QListWidgetItem(MICROSOFT_PROVIDER_NAME)
    item.setData(Qt.ItemDataRole.UserRole, MICROSOFT_PROVIDER_ID)
    self.provider_list.addItem(item)


SettingsDialog._build_provider_pages = _patched_build_provider_pages


def _patched_provider_is_available(self: SettingsDialog, provider_id: str) -> bool:
    if provider_id != MICROSOFT_PROVIDER_ID:
        return _original_provider_is_available(self, provider_id)
    return (
        self.microsoft_enabled.currentData() is True
        and bool(self.microsoft_api_key.text().strip())
    )


SettingsDialog._provider_is_available = _patched_provider_is_available


def _patched_load_all_settings(self: SettingsDialog):
    _original_load_all_settings(self)
    data = config.get_provider(MICROSOFT_PROVIDER_ID)
    self.microsoft_enabled.setCurrentIndex(1 if data.get("enabled", False) else 0)
    self.microsoft_api_key.setText(config.secrets.get("microsoft_api_key"))
    self.microsoft_source_language.setText(data.get("source_language", "en"))
    self.microsoft_target_language.setText(data.get("target_language", "ru"))
    self.microsoft_endpoint.setText(data.get("endpoint", MICROSOFT_DEFAULT_ENDPOINT))
    self.microsoft_region.setText(data.get("region", ""))


SettingsDialog._load_all_settings = _patched_load_all_settings


def _patched_save_all_settings(self: SettingsDialog):
    _original_save_all_settings(self)

    data = dict(config.get_provider(MICROSOFT_PROVIDER_ID))
    data.update(
        {
            "enabled": self.microsoft_enabled.currentData() is True,
            "source_language": self.microsoft_source_language.text().strip() or "en",
            "target_language": self.microsoft_target_language.text().strip() or "ru",
            "endpoint": self.microsoft_endpoint.text().strip() or MICROSOFT_DEFAULT_ENDPOINT,
            "region": self.microsoft_region.text().strip(),
        }
    )
    config.secrets.set("microsoft_api_key", self.microsoft_api_key.text().strip())
    config.set("providers", MICROSOFT_PROVIDER_ID, value=data)


SettingsDialog._save_all_settings = _patched_save_all_settings


def _patched_reset_provider(self: SettingsDialog, provider_id: str):
    if provider_id != MICROSOFT_PROVIDER_ID:
        return _original_reset_provider(self, provider_id)

    defaults = DEFAULT_CONFIG["providers"][MICROSOFT_PROVIDER_ID]
    self.microsoft_enabled.setCurrentIndex(1 if defaults.get("enabled", False) else 0)
    self.microsoft_source_language.setText(defaults.get("source_language", "en"))
    self.microsoft_target_language.setText(defaults.get("target_language", "ru"))
    self.microsoft_endpoint.setText(defaults.get("endpoint", MICROSOFT_DEFAULT_ENDPOINT))
    self.microsoft_region.setText(defaults.get("region", ""))


SettingsDialog._reset_provider = _patched_reset_provider


_original_provider_test_settings = settings_patch._provider_test_settings
_original_run_provider_test = settings_patch._run_provider_test


def _patched_provider_test_settings(dialog, provider_id: str) -> dict:
    result = _original_provider_test_settings(dialog, provider_id)
    if provider_id == MICROSOFT_PROVIDER_ID:
        result["endpoint"] = dialog.microsoft_endpoint.text().strip() or MICROSOFT_DEFAULT_ENDPOINT
        result["region"] = dialog.microsoft_region.text().strip()
    return result


settings_patch._provider_test_settings = _patched_provider_test_settings


def _patched_run_provider_test(provider_id: str, settings: dict):
    if provider_id != MICROSOFT_PROVIDER_ID:
        return _original_run_provider_test(provider_id, settings)

    started = time.perf_counter()
    try:
        source = str(settings.get("source_language") or "en").strip() or "en"
        target = str(settings.get("target_language") or "ru").strip() or "ru"
        translator = MicrosoftTranslateTranslator(
            api_key=str(settings.get("api_key") or "").strip(),
            source_language=source,
            target_language=target,
            endpoint=str(settings.get("endpoint") or MICROSOFT_DEFAULT_ENDPOINT).strip() or MICROSOFT_DEFAULT_ENDPOINT,
            region=str(settings.get("region") or "").strip(),
        )
        first_result = translator.translate("Hello, how are you?", source, target)
        second_result = translator.translate("Привет, как дела?", target, source)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return settings_patch._ProviderTestResult(
            provider_id=provider_id,
            success=True,
            elapsed_ms=elapsed_ms,
            message="Проверка завершена успешно.",
            en_result=str(first_result or ""),
            ru_result=str(second_result or ""),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return settings_patch._ProviderTestResult(
            provider_id=provider_id,
            success=False,
            elapsed_ms=elapsed_ms,
            message=str(exc) or exc.__class__.__name__,
        )


settings_patch._run_provider_test = _patched_run_provider_test
