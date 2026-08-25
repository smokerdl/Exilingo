from __future__ import annotations

from PyQt6.QtCore import Qt

from .chat_overlay import ChatOverlay


_original_set_input_mode = ChatOverlay.set_input_mode


def _patched_set_input_mode(self, enabled: bool):
    _original_set_input_mode(self, enabled)

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
