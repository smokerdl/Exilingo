from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QObject, QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QScrollBar,
    QTabBar,
    QPushButton,
    QStyle,
    QStyleOptionSpinBox,
    QWidget,
)


# ============================================================
# Existing settings-dialog mouse compatibility patch
# ============================================================


class _SettingsDialogMouseHandler(QObject):
    """Mouse interaction helper for the frameless settings dialog."""

    def __init__(self, dialog: QDialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.dragging = False
        self.drag_offset = None

    @staticmethod
    def _is_interactive(widget: QWidget) -> bool:
        return isinstance(
            widget,
            (
                QAbstractButton,
                QAbstractItemView,
                QAbstractSpinBox,
                QComboBox,
                QLineEdit,
                QPlainTextEdit,
                QScrollBar,
                QTabBar,
            ),
        )

    @staticmethod
    def _find_parent_spinbox(widget: QWidget):
        current = widget
        while current is not None:
            if isinstance(current, QAbstractSpinBox):
                return current
            current = current.parentWidget()
        return None

    @staticmethod
    def _spinbox_arrow_rects(widget: QAbstractSpinBox):
        option = QStyleOptionSpinBox()
        widget.initStyleOption(option)
        up_rect = widget.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxUp,
            widget,
        )
        down_rect = widget.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            QStyle.SubControl.SC_SpinBoxDown,
            widget,
        )
        return up_rect, down_rect

    @classmethod
    def _spinbox_at_event(cls, watched: QWidget, event):
        spinbox = cls._find_parent_spinbox(watched)
        if spinbox is None:
            return None, None
        global_pos = watched.mapToGlobal(event.position().toPoint())
        local_pos = spinbox.mapFromGlobal(global_pos)
        return spinbox, local_pos

    @classmethod
    def _handle_spinbox_click(cls, watched: QWidget, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        spinbox, pos = cls._spinbox_at_event(watched, event)
        if spinbox is None:
            return False

        up_rect, down_rect = cls._spinbox_arrow_rects(spinbox)
        if up_rect.isValid() and up_rect.contains(pos):
            spinbox.setValue(min(spinbox.value() + spinbox.singleStep(), spinbox.maximum()))
            return True
        if down_rect.isValid() and down_rect.contains(pos):
            spinbox.setValue(max(spinbox.value() - spinbox.singleStep(), spinbox.minimum()))
            return True

        arrow_width = max(20, min(32, spinbox.height()))
        if pos.x() < spinbox.width() - arrow_width:
            return False
        midpoint = spinbox.height() / 2
        if pos.y() < midpoint:
            spinbox.setValue(min(spinbox.value() + spinbox.singleStep(), spinbox.maximum()))
        else:
            spinbox.setValue(max(spinbox.value() - spinbox.singleStep(), spinbox.minimum()))
        return True

    @classmethod
    def _update_spinbox_cursor(cls, watched: QWidget, event) -> bool:
        spinbox, pos = cls._spinbox_at_event(watched, event)
        if spinbox is None:
            return False
        up_rect, down_rect = cls._spinbox_arrow_rects(spinbox)
        if (
            (up_rect.isValid() and up_rect.contains(pos))
            or (down_rect.isValid() and down_rect.contains(pos))
        ):
            watched.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            watched.unsetCursor()
        return True

    def eventFilter(self, watched: QObject, event) -> bool:
        if not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)

        event_type = event.type()

        if event_type == QEvent.Type.MouseButtonPress:
            if isinstance(watched, QAbstractSpinBox) or isinstance(watched, QLineEdit):
                if self._handle_spinbox_click(watched, event):
                    return True

        if event_type == QEvent.Type.MouseMove:
            if isinstance(watched, QAbstractSpinBox) or isinstance(watched, QLineEdit):
                self._update_spinbox_cursor(watched, event)

        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return super().eventFilter(watched, event)
            if self._is_interactive(watched):
                return super().eventFilter(watched, event)
            self.dragging = True
            global_pos = event.globalPosition().toPoint()
            self.drag_offset = global_pos - self.dialog.frameGeometry().topLeft()
            self.dialog.grabMouse()
            return True

        if event_type == QEvent.Type.MouseMove and self.dragging:
            global_pos = event.globalPosition().toPoint()
            self.dialog.move(global_pos - self.drag_offset)
            return True

        if event_type == QEvent.Type.MouseButtonRelease and self.dragging:
            if event.button() == Qt.MouseButton.LeftButton:
                self.dragging = False
                self.drag_offset = None
                self.dialog.releaseMouse()
                return True

        return super().eventFilter(watched, event)


def _install_mouse_handler(dialog: QDialog) -> None:
    handler = _SettingsDialogMouseHandler(dialog)
    dialog._settings_mouse_handler = handler
    dialog.installEventFilter(handler)
    for widget in dialog.findChildren(QWidget):
        widget.installEventFilter(handler)


# ============================================================
# Provider diagnostics
# ============================================================


@dataclass
class _ProviderTestResult:
    provider_id: str
    success: bool
    elapsed_ms: float
    message: str
    en_result: str = ""
    ru_result: str = ""


class _ProviderTestSignals(QObject):
    finished = pyqtSignal(object)


def _run_provider_test(provider_id: str, settings: dict) -> _ProviderTestResult:
    """Создаёт провайдер строго из текущих значений UI и выполняет два запроса."""
    from providers.google_translate import GoogleTranslateTranslator
    from providers.gemini.translator import GeminiTranslator
    from providers.groq.translator import GroqTranslator
    from providers.openrouter.translator import OpenRouterTranslator
    from providers.ollama.translator import OllamaTranslator

    started = time.perf_counter()

    try:
        source = str(settings.get("source_language") or "en").strip() or "en"
        target = str(settings.get("target_language") or "ru").strip() or "ru"
        model = str(settings.get("model") or "").strip()
        prompt = str(settings.get("system_prompt") or "").strip()

        if provider_id == "google":
            translator = GoogleTranslateTranslator(
                source_language=source,
                target_language=target,
            )
        elif provider_id == "gemini":
            translator = GeminiTranslator(
                api_key=str(settings.get("api_key") or "").strip(),
                model=model,
                system_prompt=prompt,
                source_language=source,
                target_language=target,
            )
        elif provider_id == "groq":
            translator = GroqTranslator(
                api_key=str(settings.get("api_key") or "").strip(),
                model=model,
                system_prompt=prompt,
                source_language=source,
                target_language=target,
            )
        elif provider_id == "openrouter":
            translator = OpenRouterTranslator(
                api_key=str(settings.get("api_key") or "").strip(),
                model=model,
                system_prompt=prompt,
                source_language=source,
                target_language=target,
            )
        elif provider_id == "ollama":
            translator = OllamaTranslator(
                host=str(settings.get("host") or "http://127.0.0.1:11434").strip(),
                model=model,
                system_prompt=prompt,
                source_language=source,
                target_language=target,
            )
        else:
            raise RuntimeError(f"Unknown provider: {provider_id}")

        first_result = translator.translate(
            "Hello, how are you?",
            source_language=source,
            target_language=target,
        )

        second_result = translator.translate(
            "Привет, как дела?",
            source_language=target,
            target_language=source,
        )

        elapsed_ms = (time.perf_counter() - started) * 1000
        return _ProviderTestResult(
            provider_id=provider_id,
            success=True,
            elapsed_ms=elapsed_ms,
            message="Проверка завершена успешно.",
            en_result=str(first_result or ""),
            ru_result=str(second_result or ""),
        )

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        return _ProviderTestResult(
            provider_id=provider_id,
            success=False,
            elapsed_ms=elapsed_ms,
            message=str(exc) or exc.__class__.__name__,
        )


def _provider_test_settings(dialog, provider_id: str) -> dict:
    def text_widget(name: str, default: str = "") -> str:
        widget = getattr(dialog, name, None)
        if widget is None or not hasattr(widget, "text"):
            return default
        return str(widget.text()).strip()

    if provider_id == "google":
        return {
            "source_language": text_widget("google_source", "en"),
            "target_language": text_widget("google_target", "ru"),
            "model": "",
            "system_prompt": "",
        }

    result = {
        "source_language": text_widget(f"{provider_id}_source_language", "en"),
        "target_language": text_widget(f"{provider_id}_target_language", "ru"),
        "model": text_widget(f"{provider_id}_model"),
        "system_prompt": getattr(dialog, f"{provider_id}_system_prompt").toPlainText().strip(),
    }

    if provider_id == "ollama":
        result["host"] = text_widget("ollama_host", "http://127.0.0.1:11434")
    else:
        result["api_key"] = text_widget(f"{provider_id}_api_key")

    return result


def _install_provider_test_button(dialog, provider_id: str, page: QWidget) -> None:
    layout = page.layout()
    if layout is None:
        return

    row = QHBoxLayout()
    button = QPushButton("Проверить")
    status = QLabel("Не проверено")
    status.setWordWrap(True)

    row.addWidget(button)
    row.addWidget(status, 1)
    layout.addLayout(row)

    test_state = {"thread": None, "signals": None}
    dialog.__dict__.setdefault("_provider_test_widgets", {})[provider_id] = (button, status)

    def on_click():
        button.setEnabled(False)
        status.setStyleSheet("")
        status.setText("Проверка...")

        settings = _provider_test_settings(dialog, provider_id)
        signals = _ProviderTestSignals()
        test_state["signals"] = signals

        def worker():
            result = _run_provider_test(provider_id, settings)
            signals.finished.emit(result)

        thread = threading.Thread(target=worker, daemon=True)
        test_state["thread"] = thread

        def finished(result: _ProviderTestResult):
            button.setEnabled(True)
            if result.success:
                status.setText(
                    f"✓ Работает — {result.elapsed_ms:.0f} мс\n"
                    f"EN → RU: {result.en_result}\n"
                    f"RU → EN: {result.ru_result}"
                )
                status.setStyleSheet("color: #66CCFF;")
            else:
                status.setText(
                    f"✗ Ошибка — {result.elapsed_ms:.0f} мс\n{result.message}"
                )
                status.setStyleSheet("color: #FF7777;")

        signals.finished.connect(finished)
        thread.start()

    button.clicked.connect(on_click)


# ============================================================
# Persistent Outgoing route
# ============================================================


def _outgoing_route_file(dialog=None) -> Path:
    from core.config_manager import CONFIG_FILE
    return Path(CONFIG_FILE).with_name("outgoing_route.json")


def _load_outgoing_route() -> list[str]:
    path = _outgoing_route_file()
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            route = data.get("providers") if isinstance(data, dict) else None
            if isinstance(route, list):
                return [str(item).strip().lower() for item in route if str(item).strip()]
    except Exception:
        pass
    return []


def _save_outgoing_route(route: list[str]) -> None:
    path = _outgoing_route_file()
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump({"providers": route}, handle, ensure_ascii=False, indent=4)
    except Exception:
        pass


def _install_outgoing_route(dialog) -> None:
    """Добавляет отдельную очередь Outgoing, не меняя старый routing UI."""
    list_widget = dialog.routing_channel_list

    existing = {
        list_widget.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(list_widget.count())
    }

    if "outgoing" not in existing:
        item = QListWidgetItem("Outgoing - Исходящие")
        item.setData(Qt.ItemDataRole.UserRole, "outgoing")
        list_widget.addItem(item)

    fallback = _load_outgoing_route()
    if not fallback:
        fallback = list(config.get("routing", "whisper", default=["google"]) or ["google"])
    dialog.routing_data["outgoing"] = list(fallback)

    original_channel_changed = dialog._routing_channel_changed

    def routing_channel_changed(current, previous):
        original_channel_changed(current, previous)
        if current is not None:
            channel = current.data(Qt.ItemDataRole.UserRole)
            if channel == "outgoing":
                dialog.current_routing_channel = "outgoing"
                dialog._display_routing_queue(
                    dialog.routing_data.get("outgoing", ["google"])
                )

    dialog._routing_channel_changed = routing_channel_changed
    try:
        list_widget.currentItemChanged.disconnect()
    except TypeError:
        pass
    list_widget.currentItemChanged.connect(dialog._routing_channel_changed)

    original_save = dialog._save_all_settings

    def save_all_settings():
        original_save()

        if dialog.current_routing_channel == "outgoing":
            dialog.routing_data["outgoing"] = dialog._get_current_routing_queue()

        queue = list(dialog.routing_data.get("outgoing", ["google"]))
        queue = [
            provider_id
            for provider_id in queue
            if dialog._provider_is_available(provider_id)
        ]

        unique = []
        for provider_id in queue:
            if provider_id not in unique:
                unique.append(provider_id)

        if not unique and dialog.google_enabled.isChecked():
            unique = ["google"]

        _save_outgoing_route(unique)

    dialog._save_all_settings = save_all_settings


# ============================================================
# Runtime patches
# ============================================================

from .settings_dialog import SettingsDialog
from core.translation_manager import TranslationManager
from core.translation_router import TranslationRouter
from ui.chat_overlay import ChatOverlay


_original_settings_dialog_init = SettingsDialog.__init__


def _patched_settings_dialog_init(self, *args, **kwargs):
    _original_settings_dialog_init(self, *args, **kwargs)
    _install_mouse_handler(self)

    for provider_id, page in self.provider_pages.items():
        _install_provider_test_button(self, provider_id, page)

    _install_outgoing_route(self)


SettingsDialog.__init__ = _patched_settings_dialog_init


# ------------------------------------------------------------
# TranslationRouter: outgoing uses its own route.
# ------------------------------------------------------------

_original_router_resolve_channel = TranslationRouter._resolve_channel


def _patched_router_resolve_channel(self, context, direction):
    if direction == "outgoing":
        return "outgoing"
    return _original_router_resolve_channel(self, context, direction)


TranslationRouter._resolve_channel = _patched_router_resolve_channel

_original_config_route = config.route


def _patched_config_route(channel: str):
    if channel == "outgoing":
        route = _load_outgoing_route()
        if route:
            known = set(config.data.get("providers", {}).keys())
            result = []
            for provider_id in route:
                if provider_id in known and provider_id not in result:
                    result.append(provider_id)
            if result:
                return result
        return _original_config_route("whisper")
    return _original_config_route(channel)


from core.config_manager import config
config.route = _patched_config_route


# ------------------------------------------------------------
# Outgoing echo tracking for UI highlighting.
# ------------------------------------------------------------

class _OutgoingEchoTracker:
    TTL_SECONDS = 5.0

    def __init__(self):
        self._items = deque()
        self._lock = threading.Lock()

    @staticmethod
    def _payload(channel: str, text: str) -> str:
        value = str(text or "").strip()
        if not value:
            return ""

        if channel == "whisper" and value.startswith("@"):
            value = value[1:].lstrip()
            parts = value.split(None, 1)
            return parts[1].strip() if len(parts) == 2 else ""

        if value and value[0] in {"#", "%", "$", "&"}:
            value = value[1:].lstrip()

        return value

    def remember(self, channel: str, text: str):
        payload = self._payload(channel, text).casefold()
        if not payload:
            return
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            self._items.append((channel, payload, now))

    def consume(self, channel: str, text: str) -> bool:
        payload = self._payload(channel, text).casefold()
        if not payload:
            return False
        now = time.monotonic()
        with self._lock:
            self._purge(now)
            for index, (saved_channel, saved_payload, _timestamp) in enumerate(self._items):
                if saved_channel == channel and saved_payload == payload:
                    del self._items[index]
                    return True
        return False

    def _purge(self, now: float):
        while self._items and now - self._items[0][2] > self.TTL_SECONDS:
            self._items.popleft()


_OUTGOING_ECHO_TRACKER = _OutgoingEchoTracker()

_original_manager_process_context = TranslationManager._process_context
_original_manager_enqueue = TranslationManager.enqueue


def _patched_manager_process_context(self, context):
    try:
        result = _original_manager_process_context(self, context)
        if context.direction is not None and str(context.direction).strip().lower() in {
            "outgoing", "out", "send", "sent", "to", "кому",
        }:
            _OUTGOING_ECHO_TRACKER.remember(
                context.channel,
                context.display_text or context.translated_text or context.original_text,
            )
        return result
    except Exception:
        if context.direction is not None and str(context.direction).strip().lower() in {
            "outgoing", "out", "send", "sent", "to", "кому",
        }:
            _OUTGOING_ECHO_TRACKER.remember(context.channel, context.original_text)
        raise


def _patched_manager_enqueue(self, context):
    if context.direction is None:
        if _OUTGOING_ECHO_TRACKER.consume(context.channel, context.original_text):
            context.metadata["outgoing_echo"] = True
            context.metadata["echo_sender"] = "You"
            context.source.sender = "You"
            self.logger.debug(
                "outgoing echo matched: channel=%r text=%r",
                context.channel,
                context.original_text,
            )
    return _original_manager_enqueue(self, context)


TranslationManager._process_context = _patched_manager_process_context
TranslationManager.enqueue = _patched_manager_enqueue


# ------------------------------------------------------------
# ChatOverlay: cyan for translated outgoing echoes.
# ------------------------------------------------------------

_original_overlay_add_message = ChatOverlay.add_message


def _patched_overlay_add_message(
    self,
    channel_prefix: str,
    sender: str,
    text: str,
    is_translated: bool = True,
):
    if sender == "You" and is_translated:
        from ui.chat_overlay import CHAT_NAME_COLORS
        from PyQt6.QtCore import QTimer

        name_color = CHAT_NAME_COLORS.get(channel_prefix, "#E0E0E0")
        html = (
            '<div style="margin-bottom:4px; text-shadow:1px 1px 2px black;">'
            f'<span style="color:{name_color}; font-weight:bold;">{channel_prefix}{sender}: </span>'
            f'<span style="color:#66CCFF;">{text}</span>'
            '</div>'
        )
        self.chat_history.append(html)
        QTimer.singleShot(0, self._scroll_chat_to_bottom)
        return

    return _original_overlay_add_message(
        self,
        channel_prefix,
        sender,
        text,
        is_translated,
    )


ChatOverlay.add_message = _patched_overlay_add_message
