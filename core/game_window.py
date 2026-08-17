from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Optional


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class GameWindowController:
    """Finds the Path of Exile top-level window and reports its state."""

    PROCESS_NAME_PREFIXES = (
        "pathofexile",
    )

    WINDOW_TITLE_PREFIXES = (
        "path of exile",
    )

    def __init__(self):
        self._hwnd: Optional[int] = None

    @property
    def hwnd(self) -> Optional[int]:
        return self.find_window()

    def find_window(self) -> Optional[int]:
        """Finds a visible top-level PoE window and caches its HWND."""
        found: list[int] = []

        @wintypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            title = self._window_title(hwnd).strip()
            process_name = self._process_name(hwnd)

            if self._matches_process(process_name):
                if title or user32.IsIconic(hwnd):
                    found.append(int(hwnd))
                    return False

            if self._matches_title(title):
                found.append(int(hwnd))
                return False

            return True

        user32.EnumWindows(enum_callback, 0)

        self._hwnd = found[0] if found else None
        return self._hwnd

    def is_minimized(self) -> Optional[bool]:
        """Returns True/False for PoE minimized state, or None if not found."""
        hwnd = self.find_window()
        if not hwnd:
            return None
        return bool(user32.IsIconic(hwnd))

    def _matches_process(self, process_name: str) -> bool:
        name = process_name.lower()
        return any(name.startswith(prefix) for prefix in self.PROCESS_NAME_PREFIXES)

    def _matches_title(self, title: str) -> bool:
        normalized = title.lower()
        return any(normalized.startswith(prefix) for prefix in self.WINDOW_TITLE_PREFIXES)

    @staticmethod
    def _window_title(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    @staticmethod
    def _process_name(hwnd: int) -> str:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))

        if not process_id.value:
            return ""

        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            process_id.value,
        )

        if not handle:
            return ""

        try:
            buffer_size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(buffer_size.value)

            if not kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buffer,
                ctypes.byref(buffer_size),
            ):
                return ""

            return os.path.basename(buffer.value)

        finally:
            kernel32.CloseHandle(handle)


if __name__ == "__main__":
    controller = GameWindowController()
    hwnd = controller.hwnd

    print("PoE HWND:", hex(hwnd) if hwnd else None)
    print("PoE minimized:", controller.is_minimized())
