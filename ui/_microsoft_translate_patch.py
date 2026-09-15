from __future__ import annotations

import threading
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
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
_original_available_provider_ids = SettingsDialog._available_provider_ids
_original_load_all_settings = SettingsDialog._load_all_settings
_original_save_all_settings = SettingsDialog._save_all_settings
_original_reset_provider = SettingsDialog._reset_provider
_original_init = SettingsDialog.__init__


def _build_microsoft_page(dialog: SettingsDialog) -> QWidget:
    page = QWidget()
    layout = page.layout()
    if layout is None:
        from PyQt6.QtWidgets import QVBoxLayout
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
    region.setPlaceholderText("Не требуется для Global Translator resource")
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

    test_row = QHBoxLayout()
    test_button = QPushButton("Проверить")
    test_status = QLabel("Не проверено")
    test_status.setWordWrap(True)
    test_row.addWidget(test_button)
    test_row.addWidget(test_status, 1)
    layout.addLayout(test_row)

    def run_test():
        api_key_value = dialog.microsoft_api_key.text().strip()
        source_value = dialog.microsoft_source_language.text().strip() or "en"
        target_value = dialog.microsoft_target_language.text().strip() or "ru"
        endpoint_value = dialog.microsoft_endpoint.text().strip() or MICROSOFT_DEFAULT_ENDPOINT
        region_value = dialog.microsoft_region.text().strip()

        if not api_key_value:
            test_status.setText("✗ API key не задан")
            test_status.setStyleSheet("color: #FF7777;")
            return

        test_button.setEnabled(False)
        test_status.setStyleSheet("")
        test_status.setText("Проверка...")

        def worker():
            started = time.perf_counter()
            try:
                translator = MicrosoftTranslateTranslator(
                    api_key=api_key_value,
                    source_language=source_value,
                    target_language=target_value,
                    endpoint=endpoint_value,
                    region=region_value,
                )
                en_result = translator.translate(
                    "Hello, how are you?",
                    source_language=source_value,
                    target_language=target_value,
                )
                reverse_result = translator.translate(
                    "Привет, как дела?",
                    source_language=target_value,
                    target_language=source_value,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                return True, elapsed_ms, en_result, reverse_result, ""
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                return False, elapsed_ms, "", "", str(exc) or exc.__class__.__name__

        def finished(result):
            success, elapsed_ms, en_result, reverse_result, error = result
            test_button.setEnabled(True)
            if success:
                test_status.setText(
                    f"✓ Работает — {elapsed_ms:.0f} мс\n"
                    f"{source_value.upper()} → {target_value.upper()}: {en_result}\n"
                    f"{target_value.upper()} → {source_value.upper()}: {reverse_result}"
                )
                test_status.setStyleSheet("color: #66CCFF;")
            else:
                test_status.setText(f"✗ Ошибка — {elapsed_ms:.0f} мс\n{error}")
                test_status.setStyleSheet("color: #FF7777;")

        worker_thread = threading.Thread(target=lambda: _emit_test_result(worker(), finished), daemon=True)
        worker_thread.start()

    def _emit_test_result(result, callback):
        # Qt widgets must be updated from the GUI thread. Re-enter through a zero-delay
        # single-shot timer owned by the dialog.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: callback(result))

    test_button.clicked.connect(run_test)

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

    enabled_widget = getattr(self, "microsoft_enabled", None)
    api_key_widget = getattr(self, "microsoft_api_key", None)
    return (
        enabled_widget is not None
        and enabled_widget.currentData() is True
        and api_key_widget is not None
        and bool(api_key_widget.text().strip())
    )


SettingsDialog._provider_is_available = _patched_provider_is_available


def _patched_available_provider_ids(self: SettingsDialog):
    result = list(_original_available_provider_ids(self))
    if _patched_provider_is_available(self, MICROSOFT_PROVIDER_ID):
        result.append(MICROSOFT_PROVIDER_ID)
    return result


SettingsDialog._available_provider_ids = _patched_available_provider_ids


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


def _patched_init(self: SettingsDialog, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    # _settings_dialog_patch installed its own runtime hooks first. The provider page
    # must exist before the dialog's final provider-list selection is used, so select it
    # only after our page is added by the patched _build_provider_pages above.
    if not config.get_provider(MICROSOFT_PROVIDER_ID):
        config.data["providers"][MICROSOFT_PROVIDER_ID] = dict(DEFAULT_CONFIG["providers"][MICROSOFT_PROVIDER_ID])


SettingsDialog.__init__ = _patched_init


# Ensure the provider test helper in _settings_dialog_patch can also test Microsoft
# when another part of the UI invokes the shared helper directly.
_original_run_provider_test = settings_patch._run_provider_test


def _patched_run_provider_test(provider_id: str, settings: dict):
    if provider_id != MICROSOFT_PROVIDER_ID:
        return _original_run_provider_test(provider_id, settings)

    started = time.perf_counter()
    try:
        translator = MicrosoftTranslateTranslator(
            api_key=str(settings.get("api_key") or "").strip(),
            source_language=str(settings.get("source_language") or "en").strip() or "en",
            target_language=str(settings.get("target_language") or "ru").strip() or "ru",
            endpoint=str(settings.get("endpoint") or MICROSOFT_DEFAULT_ENDPOINT).strip() or MICROSOFT_DEFAULT_ENDPOINT,
            region=str(settings.get("region") or "").strip(),
        )
        en_result = translator.translate("Hello, how are you?", settings.get("source_language", "en"), settings.get("target_language", "ru"))
        ru_result = translator.translate("Привет, как дела?", settings.get("target_language", "ru"), settings.get("source_language", "en"))
        elapsed_ms = (time.perf_counter() - started) * 1000
        return settings_patch._ProviderTestResult(
            provider_id=provider_id,
            success=True,
            elapsed_ms=elapsed_ms,
            message="Проверка завершена успешно.",
            en_result=str(en_result or ""),
            ru_result=str(ru_result or ""),
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
