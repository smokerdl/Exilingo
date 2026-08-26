from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class GlobalMouseListener(QObject):
    """Listens for global left mouse clicks and marshals them into Qt.

    The `mouse` package invokes callbacks from its own listener thread. The
    callback therefore emits a Qt signal; the actual overlay/state handling
    happens on the Qt GUI thread.
    """

    left_click = pyqtSignal()

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
        except Exception as exc:
            self._mouse = None
            self._hook = None
            raise RuntimeError(f"Failed to register global mouse listener: {exc}") from exc

    def _on_button(self, _event) -> None:
        self.left_click.emit()

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
