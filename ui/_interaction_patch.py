from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt

from .chat_overlay import ChatOverlay


_MODE_CHANGE_CALLBACK: Optional[Callable[[bool], None]] = None


def set_mode_change_callback(callback: Optional[Callable[[bool], None]]) -> None:
    global _MODE_CHANGE_CALLBACK
    _MODE_CHANGE_CALLBACK = callback


_original_set_input_mode = ChatOverlay.set_input_mode


def _patched_set_input_mode(self, enabled: bool):
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


ChatOverlay.set_input_mode = _patched_set_input_mode
