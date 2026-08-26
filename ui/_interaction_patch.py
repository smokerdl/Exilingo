from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, QCursor
from PyQt6.QtWidgets import QApplication

from .chat_overlay import ChatOverlay
from .global_mouse_listener import GlobalMouseListener


_MODE_CHANGE_CALLBACK: Optional[Callable[[bool], None]] = None


def set_mode_change_callback(callback: Optional[Callable[[bool], None]]) -> None:
    global _MODE_CHANGE_CALLBACK
    _MODE_CHANGE_CALLBACK = callback


_original_set_input_mode = ChatOverlay.set_input_mode


def _ensure_global_mouse_listener(self):
    listener = getattr(self, "_global_mouse_listener", None)
    if listener is not None:
        return

    listener = GlobalMouseListener()
    listener.left_click.connect(self._on_global_left_click)
    listener.start()
    self._global_mouse_listener = listener

    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(listener.stop)


def _on_global_left_click(self):
    """Switch interactive overlay back to click-through on an outside LMB click."""
    if not self.is_input_mode:
        return

    cursor_pos = QCursor.pos()
    if not self.frameGeometry().contains(cursor_pos):
        self.set_input_mode(False)


def _patched_set_input_mode(self, enabled: bool):
    _ensure_global_mouse_listener(self)
    _original_set_input_mode(self, enabled)

    if _MODE_CHANGE_CALLBACK is not None:
        try:
            _MODE_CHANGE_CALLBACK(bool(enabled))
        except Exception:
            pass

    if enabled:
        # Entering interactive mode must not put the caret into the input
        # field automatically. The user can click the field when they want to
        # type; clicking outside the Overlay can then return focus to PoE.
        try:
            self.input_field.clearFocus()
            self.chat_history.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass


ChatOverlay._on_global_left_click = _on_global_left_click
ChatOverlay.set_input_mode = _patched_set_input_mode
