from __future__ import annotations

from typing import Optional


class OverlayStateController:
    """Separates user visibility intent from PoE visibility."""

    def __init__(self, app):
        self.app = app
        self.overlay = app.overlay
        self.game_window_controller = app.game_window_controller
        self.logger = app.logger
        self.user_visible = True
        self.game_visible: Optional[bool] = None
        self.desired_input_mode = bool(self.overlay.is_input_mode)

    def set_initial_game_state(self, foreground: Optional[bool]) -> None:
        self.game_visible = foreground
        self.reconcile()

    def on_game_focus_changed(self, focused: bool) -> None:
        self.game_visible = bool(focused)
        self.reconcile()

    def set_user_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if visible == self.user_visible:
            self.reconcile()
            return

        self.user_visible = visible
        if not visible:
            self.desired_input_mode = bool(self.overlay.is_input_mode)
            if self.overlay.is_input_mode:
                self.overlay.set_input_mode(False)
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

        self.overlay.show()
        self.overlay.raise_()

        target_mode = bool(self.desired_input_mode)
        if self.overlay.is_input_mode != target_mode:
            self.overlay.set_input_mode(target_mode)

    def manual_show(self) -> None:
        self.user_visible = True
        self.reconcile()

    def manual_hide(self) -> None:
        self.user_visible = False
        self.desired_input_mode = bool(self.overlay.is_input_mode)
        if self.overlay.is_input_mode:
            self.overlay.set_input_mode(False)
        self.overlay.hide()
