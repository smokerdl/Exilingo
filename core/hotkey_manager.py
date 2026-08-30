from __future__ import annotations

from typing import Callable, Dict

from .logger import get_logger

DEFAULT_HOTKEYS = {
    "send_message": "f5",
    "toggle_mode": "enter",
    "toggle_visibility": "f10",
}


class HotkeyManager:
    """Registers Exilingo global hotkeys from the current configuration."""

    def __init__(self, callbacks: Dict[str, Callable[[], None]]):
        self.logger = get_logger("Hotkey")
        self.callbacks = callbacks
        self._keyboard = None
        self._handles: Dict[str, object] = {}
        self.reload()

    def _read_config(self) -> Dict[str, str]:
        from .config_manager import config

        stored = config.get("hotkeys", default={})
        if not isinstance(stored, dict):
            stored = {}

        result = {}
        for name, default in DEFAULT_HOTKEYS.items():
            if name not in stored:
                result[name] = default
            else:
                result[name] = str(stored.get(name) or "").strip().lower()
        return result

    def reload(self) -> None:
        self.stop()

        try:
            import keyboard

            self._keyboard = keyboard
            hotkeys = self._read_config()
            seen = {}

            for action, callback in self.callbacks.items():
                hotkey = hotkeys.get(action, "").strip().lower()
                if not hotkey:
                    continue
                if hotkey in seen:
                    self.logger.error(
                        "Hotkey conflict: %r is assigned to both %s and %s.",
                        hotkey,
                        seen[hotkey],
                        action,
                    )
                    continue

                seen[hotkey] = action
                handle = keyboard.add_hotkey(
                    hotkey,
                    callback,
                    suppress=False,
                    trigger_on_release=False,
                )
                self._handles[action] = handle
                self.logger.info("Hotkey registered: %s=%s", action, hotkey)

        except Exception as exc:
            self.logger.error(
                "Failed to register configured hotkeys: %s",
                exc,
                exc_info=True,
            )
            self._keyboard = None

    def stop(self) -> None:
        keyboard_module = self._keyboard
        if keyboard_module is None:
            return

        for action, handle in list(self._handles.items()):
            try:
                keyboard_module.remove_hotkey(handle)
                self.logger.debug("Hotkey unregistered: %s", action)
            except Exception:
                self.logger.debug(
                    "Failed to unregister hotkey: %s",
                    action,
                    exc_info=True,
                )

        self._handles.clear()
        self._keyboard = None

    def update_from_config(self) -> None:
        self.reload()
