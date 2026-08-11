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
    def _find_parent_spinbox(widget: QWidget):
        """Return the QAbstractSpinBox that owns an internal editor widget."""
        current = widget

        while current is not None:
            if isinstance(current, QAbstractSpinBox):
                return current
            current = current.parentWidget()

        return None

    @staticmethod
    def _spinbox_arrow_rects(widget: QAbstractSpinBox):
        """Return the exact ▲/▼ rectangles used by the active Qt style."""
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
        """Return (spinbox, local_position) for a spinbox or its editor child."""
        spinbox = cls._find_parent_spinbox(watched)

        if spinbox is None:
            return None, None

        global_pos = watched.mapToGlobal(
            event.position().toPoint(),
        )
        local_pos = spinbox.mapFromGlobal(
            global_pos,
        )

        return spinbox, local_pos

    @classmethod
    def _handle_spinbox_click(cls, watched: QWidget, event) -> bool:
        """Handle visible QSpinBox ▲/▼ buttons, including clicks on its editor."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        spinbox, pos = cls._spinbox_at_event(
            watched,
            event,
        )

        if spinbox is None:
            return False

        up_rect, down_rect = cls._spinbox_arrow_rects(
            spinbox,
        )

        if up_rect.isValid() and up_rect.contains(pos):
            spinbox.setValue(
                min(
                    spinbox.value() + spinbox.singleStep(),
                    spinbox.maximum(),
                )
            )
            return True

        if down_rect.isValid() and down_rect.contains(pos):
            spinbox.setValue(
                max(
                    spinbox.value() - spinbox.singleStep(),
                    spinbox.minimum(),
                )
            )
            return True

        # Fallback for styles that do not expose useful sub-control geometry.
        arrow_width = max(
            20,
            min(32, spinbox.height()),
        )

        if pos.x() < spinbox.width() - arrow_width:
            return False

        midpoint = spinbox.height() / 2

        if pos.y() < midpoint:
            spinbox.setValue(
                min(
                    spinbox.value() + spinbox.singleStep(),
                    spinbox.maximum(),
                )
            )
        else:
            spinbox.setValue(
                max(
                    spinbox.value() - spinbox.singleStep(),
                    spinbox.minimum(),
                )
            )

        return True

    @classmethod
    def _update_spinbox_cursor(cls, watched: QWidget, event) -> bool:
        """Show an arrow cursor over ▲/▼ even when the internal editor receives the event."""
        spinbox, pos = cls._spinbox_at_event(
            watched,
            event,
        )

        if spinbox is None:
            return False

        up_rect, down_rect = cls._spinbox_arrow_rects(
            spinbox,
        )

        if (
            (up_rect.isValid() and up_rect.contains(pos))
            or (down_rect.isValid() and down_rect.contains(pos))
        ):
            watched.setCursor(
                Qt.CursorShape.ArrowCursor,
            )
        else:
            # Return control of the cursor to the native widget/editor.
            watched.unsetCursor()

        return True

    def eventFilter(self, watched: QObject, event) -> bool:
        if not isinstance(watched, QWidget):
            return super().eventFilter(watched, event)

        event_type = event.type()

        # ----------------------------------------------------
        # Spin-box arrows
        # ----------------------------------------------------

        if event_type == QEvent.Type.MouseButtonPress:
            if isinstance(watched, QAbstractSpinBox) or isinstance(watched, QLineEdit):
                if self._handle_spinbox_click(watched, event):
                    return True

        if event_type == QEvent.Type.MouseMove:
            if isinstance(watched, QAbstractSpinBox) or isinstance(watched, QLineEdit):
                self._update_spinbox_cursor(watched, event)

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
