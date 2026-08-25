from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QKeySequenceEdit,
    QMessageBox,
)

from core.config_manager import config
from core.hotkey_manager import DEFAULT_HOTKEYS
from .settings_dialog import SettingsDialog


_RUNTIME_APPLY_CALLBACK: Optional[Callable[[], None]] = None
_HOTKEY_RELOAD_CALLBACK: Optional[Callable[[], None]] = None


def set_runtime_callbacks(
    apply_callback: Optional[Callable[[], None]],
    hotkey_reload_callback: Optional[Callable[[], None]],
) -> None:
    global _RUNTIME_APPLY_CALLBACK, _HOTKEY_RELOAD_CALLBACK
    _RUNTIME_APPLY_CALLBACK = apply_callback
    _HOTKEY_RELOAD_CALLBACK = hotkey_reload_callback


def _ensure_hotkeys() -> dict:
    stored = config.get("hotkeys", default={})
    if not isinstance(stored, dict):
        stored = {}

    result = {}
    changed = False
    for name, default in DEFAULT_HOTKEYS.items():
        if name not in stored:
            result[name] = default
            changed = True
        else:
            result[name] = str(stored.get(name) or "").strip().lower()

    if changed:
        config.set("hotkeys", value=result)
    return result


def _sequence_to_hotkey(editor: QKeySequenceEdit) -> str:
    value = editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
    return value.strip().lower()


def _set_editor_value(editor: QKeySequenceEdit, value: str) -> None:
    editor.setKeySequence(QKeySequence(str(value or "").strip()))


_original_settings_init = SettingsDialog.__init__
_original_settings_save = SettingsDialog._save_all_settings


def _install_hotkey_group(dialog: SettingsDialog) -> None:
    if hasattr(dialog, "hotkey_send_editor"):
        return

    hotkeys = _ensure_hotkeys()
    general_tab = dialog.tabs.widget(0)
    layout = general_tab.layout()
    if layout is None:
        return

    group = QGroupBox("Горячие клавиши")
    form = QFormLayout(group)

    dialog.hotkey_send_editor = QKeySequenceEdit()
    dialog.hotkey_toggle_editor = QKeySequenceEdit()
    dialog.hotkey_visibility_editor = QKeySequenceEdit()

    form.addRow("Отправить сообщение:", dialog.hotkey_send_editor)
    form.addRow("Переключить режим Overlay:", dialog.hotkey_toggle_editor)
    form.addRow("Показать / скрыть Overlay:", dialog.hotkey_visibility_editor)

    info = QLabel("Горячую клавишу можно очистить, чтобы отключить действие.")
    info.setWordWrap(True)
    form.addRow(info)

    _set_editor_value(dialog.hotkey_send_editor, hotkeys["send_message"])
    _set_editor_value(dialog.hotkey_toggle_editor, hotkeys["toggle_mode"])
    _set_editor_value(dialog.hotkey_visibility_editor, hotkeys["toggle_visibility"])

    layout.addWidget(group)


def _save_hotkeys(dialog: SettingsDialog) -> None:
    values = {
        "send_message": _sequence_to_hotkey(dialog.hotkey_send_editor),
        "toggle_mode": _sequence_to_hotkey(dialog.hotkey_toggle_editor),
        "toggle_visibility": _sequence_to_hotkey(dialog.hotkey_visibility_editor),
    }

    seen = {}
    labels = {
        "send_message": "Отправить сообщение",
        "toggle_mode": "Переключить режим Overlay",
        "toggle_visibility": "Показать / скрыть Overlay",
    }
    for action, hotkey in values.items():
        if not hotkey:
            continue
        if hotkey in seen:
            raise ValueError(
                f"Горячая клавиша {hotkey.upper()} уже назначена для действий "
                f"'{seen[hotkey]}' и '{labels[action]}'."
            )
        seen[hotkey] = labels[action]

    config.set("hotkeys", value=values)


def _patched_settings_save(self):
    _save_hotkeys(self)
    _original_settings_save(self)


def _apply_runtime(dialog: SettingsDialog) -> None:
    if _RUNTIME_APPLY_CALLBACK is not None:
        _RUNTIME_APPLY_CALLBACK()
    if _HOTKEY_RELOAD_CALLBACK is not None:
        _HOTKEY_RELOAD_CALLBACK()


def _install_dialog_buttons(dialog: SettingsDialog) -> None:
    button_box = dialog.findChild(QDialogButtonBox)
    if button_box is None:
        return

    try:
        button_box.accepted.disconnect()
    except Exception:
        pass
    try:
        button_box.rejected.disconnect()
    except Exception:
        pass
    try:
        button_box.clicked.disconnect()
    except Exception:
        pass

    button_box.setStandardButtons(
        QDialogButtonBox.StandardButton.Ok
        | QDialogButtonBox.StandardButton.Cancel
        | QDialogButtonBox.StandardButton.Apply
    )

    def handle_click(button):
        role = button_box.buttonRole(button)

        if role == QDialogButtonBox.ButtonRole.RejectRole:
            dialog.reject()
            return

        try:
            dialog._save_all_settings()
            _apply_runtime(dialog)
        except Exception as exc:
            QMessageBox.critical(dialog, "Ошибка сохранения", str(exc))
            return

        if role == QDialogButtonBox.ButtonRole.AcceptRole:
            dialog.accept()

    button_box.clicked.connect(handle_click)


def _patched_settings_init(self, *args, **kwargs):
    _original_settings_init(self, *args, **kwargs)
    _install_hotkey_group(self)
    _install_dialog_buttons(self)


SettingsDialog._save_all_settings = _patched_settings_save
SettingsDialog.__init__ = _patched_settings_init
