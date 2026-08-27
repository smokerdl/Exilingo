from __future__ import annotations

import ctypes
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer

from .chat_overlay import ChatOverlay
from .global_mouse_listener import GlobalMouseListener


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

        # Temporary diagnostics: observe the global LMB path while interactive.
        if not hasattr(self, "_mouse_diagnostics"):
            try:
                self._mouse_diagnostics = GlobalMouseListener()
                self._mouse_diagnostics.left_click.connect(
                    lambda x, y: _log_global_left_click(self, x, y)
                )
                self._mouse_diagnostics.start()
            except Exception as exc:
                print(f"[MouseDiagnostics] listener setup failed: {exc}")


def _log_global_left_click(overlay: ChatOverlay, x: int, y: int) -> None:
    """Log the exact state when a global LMB event reaches the Qt thread."""
    try:
        user32 = ctypes.windll.user32
        hwnd = int(overlay.winId())
        under_cursor = int(user32.WindowFromPoint(ctypes.wintypes.POINT(x, y)))
        foreground = int(user32.GetForegroundWindow())
        active = int(user32.GetActiveWindow())

        rect = ctypes.wintypes.RECT()
        rect_ok = bool(user32.GetWindowRect(hwnd, ctypes.byref(rect)))
        inside = bool(
            rect_ok
            and rect.left <= x < rect.right
            and rect.top <= y < rect.bottom
        )

        print(
            "[MouseDiagnostics] LMB received: "
            f"cursor=({x},{y}), "
            f"under_cursor=0x{under_cursor:X}, "
            f"input_mode={overlay.is_input_mode}, "
            f"inside_overlay={inside}, "
            f"qt_active={overlay.isActiveWindow()}, "
            f"foreground=0x{foreground:X}, "
            f"active=0x{active:X}"
        )
        if rect_ok:
            print(
                "[MouseDiagnostics] overlay_rect="
                f"({rect.left},{rect.top},{rect.right},{rect.bottom})"
            )

        # Capture the state after Windows/Qt processes the activation caused by
        # this click. No state is modified here.
        QTimer.singleShot(50, lambda: _log_after_global_click(overlay))
    except Exception as exc:
        print(f"[MouseDiagnostics] click inspection failed: {exc}")


def _log_after_global_click(overlay: ChatOverlay) -> None:
    try:
        user32 = ctypes.windll.user32
        foreground = int(user32.GetForegroundWindow())
        active = int(user32.GetActiveWindow())
        print(
            "[MouseDiagnostics] after 50ms: "
            f"input_mode={overlay.is_input_mode}, "
            f"qt_active={overlay.isActiveWindow()}, "
            f"foreground=0x{foreground:X}, "
            f"active=0x{active:X}"
        )
    except Exception as exc:
        print(f"[MouseDiagnostics] after-click inspection failed: {exc}")


ChatOverlay.set_input_mode = _patched_set_input_mode
