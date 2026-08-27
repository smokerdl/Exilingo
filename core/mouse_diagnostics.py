from __future__ import annotations

import ctypes

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


user32 = ctypes.windll.user32


class GlobalMouseDiagnostics(QObject):
    """Temporary global left-click diagnostics.

    The mouse package invokes its callback from a worker thread. The callback
    only emits a Qt signal; all inspection of the Qt overlay happens on the
    GUI thread.
    """

    click_received = pyqtSignal(int, int, str)

    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self._mouse = None
        self._hook = None
        self.click_received.connect(self._on_click)

    def start(self) -> None:
        if self._mouse is not None:
            return
        try:
            import mouse

            self._mouse = mouse
            self._hook = mouse.hook(self._mouse_callback)
            print("[MouseDiagnostics] Global mouse diagnostics started.")
        except Exception as exc:
            print(f"[MouseDiagnostics] Failed to start: {exc}")
            self._mouse = None
            self._hook = None

    def stop(self) -> None:
        if self._mouse is None:
            return
        try:
            if self._hook is not None:
                self._mouse.unhook(self._hook)
        except Exception as exc:
            print(f"[MouseDiagnostics] Failed to stop: {exc}")
        finally:
            self._hook = None
            self._mouse = None

    def _mouse_callback(self, event) -> None:
        try:
            if getattr(event, "event_type", "") != "down":
                return
            if str(getattr(event, "button", "")).lower() != "left":
                return

            x, y = user32.GetCursorPos if False else (0, 0)
            point = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            self.click_received.emit(int(point.x), int(point.y), "left")
        except Exception as exc:
            print(f"[MouseDiagnostics] callback failed: {exc}")

    def _on_click(self, x: int, y: int, button: str) -> None:
        try:
            overlay_hwnd = int(self.overlay.winId())
            point = ctypes.wintypes.POINT(x, y)
            under_cursor = int(user32.WindowFromPoint(point))

            rect = ctypes.wintypes.RECT()
            rect_ok = bool(user32.GetWindowRect(overlay_hwnd, ctypes.byref(rect)))
            inside = bool(
                rect_ok
                and rect.left <= x < rect.right
                and rect.top <= y < rect.bottom
            )

            foreground = int(user32.GetForegroundWindow())
            active = int(user32.GetActiveWindow())

            print(
                "[MouseDiagnostics] "
                f"LMB: cursor=({x},{y}), "
                f"overlay_hwnd=0x{overlay_hwnd:X}, "
                f"under_cursor=0x{under_cursor:X}, "
                f"overlay_rect="
                f"({rect.left},{rect.top},{rect.right},{rect.bottom}) "
                if rect_ok
                else "[MouseDiagnostics] LMB: overlay_rect=<unavailable> "
            )
            if rect_ok:
                print(
                    "[MouseDiagnostics] "
                    f"LMB state: inside={inside}, "
                    f"input_mode={self.overlay.is_input_mode}, "
                    f"qt_active={self.overlay.isActiveWindow()}, "
                    f"foreground=0x{foreground:X}, "
                    f"active=0x{active:X}"
                )

            # Give Windows/Qt a moment to process the click and activation
            # change, then capture the resulting state without changing it.
            QTimer.singleShot(50, self._log_after_click)
        except Exception as exc:
            print(f"[MouseDiagnostics] click inspection failed: {exc}")

    def _log_after_click(self) -> None:
        try:
            hwnd = int(self.overlay.winId())
            foreground = int(user32.GetForegroundWindow())
            active = int(user32.GetActiveWindow())
            print(
                "[MouseDiagnostics] after 50ms: "
                f"input_mode={self.overlay.is_input_mode}, "
                f"qt_active={self.overlay.isActiveWindow()}, "
                f"foreground=0x{foreground:X}, "
                f"active=0x{active:X}"
            )
        except Exception as exc:
            print(f"[MouseDiagnostics] after-click inspection failed: {exc}")
