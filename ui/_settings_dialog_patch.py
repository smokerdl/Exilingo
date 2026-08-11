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
    def _handle_spinbox_click(widget: QAbstractSpinBox, event) -> bool:
        """Handle the visible QSpinBox ▲/▼ buttons explicitly.

        The frameless-dialog event filter can interfere with Qt's native
        spin-box mouse handling. Use the style's actual button rectangles
        when available, with a geometry fallback for custom styles.

        We change the value directly rather than calling stepUp()/stepDown(),
        so the visible ▲ always increases the numeric value and ▼ always
        decreases it, regardless of inverted-control settings.
        """
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        pos = event.position().toPoint()

        # Prefer the exact rectangles used by the active Qt style.
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

        if up_rect.isValid() and up_rect.contains(pos):
            widget.setValue(
                min(widget.value() + widget.singleStep(), widget.maximum())
            )
            return True

        if down_rect.isValid() and down_rect.contains(pos):
            widget.setValue(
                max(widget.value() - widget.singleStep(), widget.minimum())
            )
            return True

        # Fallback for styles that do not expose useful sub-control geometry.
        arrow_width = max(20, min(32, widget.height()))
        if pos.x() < widget.width() - arrow_width:
            return False

        midpoint = widget.height() / 2
        if pos.y() < midpoint:
            widget.setValue(
                min(widget.value() + widget.singleStep(), widget.maximum())
            )
        else:
            widget.setValue(
                max(widget.value() - widget.singleStep(), widget.minimum())
            )

        return True

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


# Import only after the handler class is defined. ui.__init__ imports this
# module before main.py imports SettingsDialog, so the class can be wrapped
# without changing the existing settings dialog implementation.
from .settings_dialog import SettingsDialog


_original_settings_dialog_init = SettingsDialog.__init__


def _patched_settings_dialog_init(self, *args, **kwargs):
    _original_settings_dialog_init(self, *args, **kwargs)
    _install_mouse_handler(self)


SettingsDialog.__init__ = _patched_settings_dialog_init
