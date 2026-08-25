from __future__ import annotations

from typing import Optional


class OverlayStateController:
    """Separates user visibility intent from PoE visibility and mode intent."""

    def __init__(self, app):
        self.app = app
        self.overlay = app.overlay
        self.game_window_controller = app.game_window_controller
        self.logger = app.logger
        self.user_visible = True
        self.game_visible: Optional[bool] = None
        self.desired_input_mode = bool(self.overlay.is_input_mode)
        self._changing_mode = False

    def set_initial_game_state(self, foreground: Optional[bool]) -> None:
        self.game_visible = foreground
        self.reconcile()

    def on_game_focus_changed(self, focused: bool) -> None:
        self.game_visible = bool(focused)
        self.reconcile()

    def on_overlay_mode_changed(self, enabled: bool) -> None:
        if self._changing_mode:
            return
        self.desired_input_mode = bool(enabled)

    def _set_mode(self, enabled: bool) -> None:
        if self.overlay.is_input_mode == bool(enabled):
            return
        self._changing_mode = True
        try:
            self.overlay.set_input_mode(bool(enabled))
        finally:
            self._changing_mode = False

    def set_user_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self.user_visible:
            self.reconcile()
            return

        if not visible:
            self.desired_input_mode = bool(self.overlay.is_input_mode)
            self.user_visible = False
            if self.overlay.is_input_mode:
                self._set_mode(False)
        else:
            self.user_visible = True

        self.reconcile()

    def toggle_user_visibility(self) -> None:
        self.set_user_visible(not self.user_visible)

    def set_desired_input_mode(self, enabled: bool) -> None:
        self.desired_input_mode = bool(enabled)
        if not self.user_visible:
            return
        self.reconcile()

    def reconcile(self) -> None:
        should_show = self.user_visible and self.game_visible is not False

        if not should_show:
            self.overlay.hide()
            return

        if not self.overlay.isVisible():
            self.overlay.show()
        self.overlay.raise_()
        self._set_mode(self.desired_input_mode)

    def manual_show(self) -> None:
        self.user_visible = True
        if self.game_visible is False:
            self.overlay.show()
            self.overlay.raise_()
            self._set_mode(self.desired_input_mode)
            return
        self.reconcile()

    def manual_hide(self) -> None:
        self.set_user_visible(False)
        self.overlay.hide()
