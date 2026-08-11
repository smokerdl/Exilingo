from __future__ import annotations

from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QDialog,
    QLineEdit,
    QPlainTextEdit,
    QListWidget,
    QScrollBar,
    QTabBar,
    QStyle,
    QStyleOptionSpinBox,
    QWidget,
)


class _SettingsDialogMouseHandler(QObject):
    """Mouse interaction helper for the frameless settings dialog.

    The dialog intentionally has no native title bar, so it needs its own
    drag handling.  Interactive controls keep their normal mouse behavior.
    Spin-box arrow clicks are handled explicitly using Qt's own hit-testing,
    which keeps the behavior aligned with the actual platform/style buttons.
    """

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
    def _handle_spinbox_click(widget: QAbstractSpinBox, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        option = QStyleOptionSpinBox()
        widget.initStyleOption(option)

        sub_control = widget.style().hitTestComplexControl(
            QStyle.ComplexControl.CC_SpinBox,
            option,
            event.position().toPoint(),
            widget,
        )

        if sub_control == QStyle.SubControl.SC_SpinBoxUp:
            widget.stepUp()
            return True

        if sub_control == QStyle.SubControl.SC_SpinBoxDown:
            widget.stepDown()
            return True

        return False

    def eventFilter(self, watched: QObject, event) -> bool:
        if not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)

        event_type = event.type()

        # ----------------------------------------------------
        # Spin-box arrows
        # ----------------------------------------------------

        if (
            event_type == QEvent.Type.MouseButtonPress
            and isinstance(watched, QAbstractSpinBox)
        ):
            if self._handle_spinbox_click(watched, event):
                return True

        # ----------------------------------------------------
        # Frameless dialog dragging
        # ----------------------------------------------------

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

    # Keep a Python reference on the dialog as well as the QObject parent,
    # so the handler cannot be garbage-collected while the dialog is alive.
    dialog._settings_mouse_handler = handler

    dialog.installEventFilter(handler)

    for widget in dialog.findChildren(QWidget):
        widget.installEventFilter(handler)


# Import only after the handler class is defined.  ui.__init__ imports this
# module before main.py imports SettingsDialog, so the class can be wrapped
# without changing the existing settings dialog implementation.
from .settings_dialog import SettingsDialog


_original_settings_dialog_init = SettingsDialog.__init__


def _patched_settings_dialog_init(self, *args, **kwargs):
    _original_settings_dialog_init(self, *args, **kwargs)
    _install_mouse_handler(self)


SettingsDialog.__init__ = _patched_settings_dialog_init
