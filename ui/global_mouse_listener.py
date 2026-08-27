from __future__ import annotations

import ctypes

from PyQt6.QtCore import QObject, pyqtSignal


class GlobalMouseListener(QObject):
    """Temporary global left-click diagnostics for overlay mode investigation.

    The `mouse` package invokes callbacks from its own listener thread. The
    callback therefore emits a Qt signal; the actual inspection happens on
    the Qt GUI thread.
    """

    left_click = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self._mouse = None
        self._hook = None

    def start(self) -> None:
        if self._hook is not None:
            return

        try:
            import mouse

            self._mouse = mouse
            self._hook = mouse.on_button(
                self._on_button,
                buttons=("left",),
                types=("down",),
            )
            print("[MouseDiagnostics] Global mouse diagnostics started.")
        except Exception as exc:
            self._mouse = None
            self._hook = None
            raise RuntimeError(f"Failed to register global mouse listener: {exc}") from exc

    def _on_button(self, _event) -> None:
        try:
            point = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            self.left_click.emit(int(point.x), int(point.y))
        except Exception as exc:
            print(f"[MouseDiagnostics] callback failed: {exc}")

    def stop(self) -> None:
        mouse_module = self._mouse
        hook = self._hook
        self._hook = None
        self._mouse = None

        if mouse_module is None or hook is None:
            return

        try:
            mouse_module.unhook(hook)
        except Exception:
            pass
