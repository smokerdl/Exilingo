from __future__ import annotations

import ctypes
import time
from typing import Optional, Tuple

from core.config_manager import config


# ============================================================
# Windows API
# ============================================================

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D


# ============================================================
# GameChatSender
# ============================================================


class GameChatSender:
    """
    Физическая отправка готового сообщения в игровой чат Path of Exile.

    Pipeline:

        координата
          ↓
        mouse move
          ↓
        left click
          ↓
        Clipboard
          ↓
        Ctrl+V
          ↓
        Enter

    Этот класс намеренно не знает ничего о переводах и каналах.
    Он получает уже полностью подготовленный текст.
    """

    DEFAULT_CLICK_DELAY = 0.10
    DEFAULT_PASTE_DELAY = 0.10
    DEFAULT_ENTER_DELAY = 0.10

    # ========================================================
    # Debug
    # ========================================================

    @staticmethod
    def _debug(message: str):
        """Печатает подробную информацию о стадии отправки."""
        print(f"[GameChatSender][DEBUG] {message}", flush=True)

    @staticmethod
    def _window_info(hwnd: int) -> str:
        """Возвращает краткую информацию о Windows-окне."""
        if not hwnd:
            return "HWND=0"

        title_buffer = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(
            hwnd,
            title_buffer,
            len(title_buffer),
        )

        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(
            hwnd,
            class_buffer,
            len(class_buffer),
        )

        return (
            f"HWND=0x{int(hwnd):X}, "
            f"class='{class_buffer.value}', "
            f"title='{title_buffer.value}'"
        )

    @classmethod
    def _debug_foreground_window(cls, stage: str):
        hwnd = user32.GetForegroundWindow()
        cls._debug(
            f"{stage}: foreground -> {cls._window_info(hwnd)}"
        )

    @classmethod
    def _debug_window_at_point(cls, x: int, y: int):
        point = ctypes.wintypes.POINT(
            int(x),
            int(y),
        )

        hwnd = user32.WindowFromPoint(point)

        cls._debug(
            f"WindowFromPoint({x}, {y}) -> "
            f"{cls._window_info(hwnd)}"
        )

    # ========================================================
    # Конфигурация
    # ========================================================

    @staticmethod
    def get_input_point() -> Optional[Tuple[int, int]]:
        point = config.get(
            "game_chat",
            "input_point",
            default=None,
        )

        if not isinstance(point, dict):
            return None

        try:
            x = int(point["x"])
            y = int(point["y"])
        except (KeyError, TypeError, ValueError):
            return None

        # 0,0 означает "не откалибровано".
        if x == 0 and y == 0:
            return None

        return x, y

    @staticmethod
    def set_input_point(
        x: int,
        y: int,
    ):
        config.set(
            "game_chat",
            "input_point",
            value={
                "x": int(x),
                "y": int(y),
            },
        )

    # ========================================================
    # Отправка
    # ========================================================

    def send(
        self,
        text: str,
        *,
        point: Optional[Tuple[int, int]] = None,
    ) -> bool:
        """Отправляет готовый текст в игровой чат."""

        self._debug("========== BEGIN SEND ==========")
        self._debug(f"raw text={text!r}")

        if not text:
            self._debug("ABORT: пустое сообщение")
            return False

        text = text.strip()

        if not text:
            self._debug("ABORT: сообщение состоит только из пробелов")
            return False

        if point is None:
            point = self.get_input_point()

        self._debug(f"input point={point!r}")

        if point is None:
            self._debug("ABORT: координата игрового чата не настроена")
            return False

        x, y = point

        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)

        self._debug(
            f"screen={screen_width}x{screen_height}, point=({x},{y})"
        )

        if not (0 <= x < screen_width and 0 <= y < screen_height):
            self._debug(
                f"ABORT: некорректная координата ({x}, {y})"
            )
            return False

        self._debug_foreground_window("before click")
        self._debug_window_at_point(x, y)

        try:
            self._debug("STAGE 1/5: SetCursorPos")
            self._move_cursor(x, y)

            cursor = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            self._debug(
                f"cursor after move=({cursor.x},{cursor.y})"
            )

            time.sleep(self.DEFAULT_CLICK_DELAY)

            self._debug("STAGE 2/5: left mouse click")
            self._click_at_current_position()

            time.sleep(self.DEFAULT_CLICK_DELAY)
            self._debug_foreground_window("after click")

            self._debug("STAGE 3/5: prepare Clipboard")
            self._set_clipboard_text(text)
            self._debug("Clipboard prepared successfully")

            time.sleep(self.DEFAULT_PASTE_DELAY)

            self._debug("STAGE 4/5: Ctrl+V")
            self._paste()

            time.sleep(self.DEFAULT_PASTE_DELAY)

            self._debug("STAGE 5/5: Enter")
            self._press_key(VK_RETURN)

            time.sleep(self.DEFAULT_ENTER_DELAY)

            self._debug_foreground_window("after Enter")
            self._debug("========== SEND COMPLETE ==========")

            return True

        except Exception as e:
            self._debug(
                f"SEND FAILED: {type(e).__name__}: {e}"
            )
            self._debug("========== SEND FAILED ==========")
            return False

    # ========================================================
    # Mouse
    # ========================================================

    @staticmethod
    def _move_cursor(
        x: int,
        y: int,
    ):
        if not user32.SetCursorPos(
            int(x),
            int(y),
        ):
            raise RuntimeError("SetCursorPos() не удался.")

    @staticmethod
    def _click_at_current_position():
        # MOUSEEVENTF_LEFTDOWN = 0x0002
        # MOUSEEVENTF_LEFTUP   = 0x0004
        user32.mouse_event(
            0x0002,
            0,
            0,
            0,
            0,
        )

        user32.mouse_event(
            0x0004,
            0,
            0,
            0,
            0,
        )

    # ========================================================
    # Keyboard
    # ========================================================

    @staticmethod
    def _press_key(
        virtual_key: int,
    ):
        user32.keybd_event(
            virtual_key,
            0,
            0,
            0,
        )

        user32.keybd_event(
            virtual_key,
            0,
            KEYEVENTF_KEYUP,
            0,
        )

    # ========================================================
    # Clipboard
    # ========================================================

    @staticmethod
    def _set_clipboard_text(
        text: str,
    ):
        """
        Помещает Unicode-текст в системный Clipboard.

        Важно: для 64-bit Windows явно задаём типы WinAPI
        указателей. Без этого ctypes может трактовать HANDLE
        как 32-bit int и обрезать адрес памяти.
        """

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        data = (text + "\0").encode("utf-16-le")

        # -------------------------------
        # kernel32 prototypes
        # -------------------------------

        kernel32.GlobalAlloc.argtypes = [
            ctypes.c_uint,
            ctypes.c_size_t,
        ]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p

        kernel32.GlobalLock.argtypes = [
            ctypes.c_void_p,
        ]
        kernel32.GlobalLock.restype = ctypes.c_void_p

        kernel32.GlobalUnlock.argtypes = [
            ctypes.c_void_p,
        ]
        kernel32.GlobalUnlock.restype = ctypes.c_bool

        kernel32.GlobalFree.argtypes = [
            ctypes.c_void_p,
        ]
        kernel32.GlobalFree.restype = ctypes.c_void_p

        # -------------------------------
        # user32 prototypes
        # -------------------------------

        user32.OpenClipboard.argtypes = [
            ctypes.c_void_p,
        ]
        user32.OpenClipboard.restype = ctypes.c_bool

        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_bool

        user32.SetClipboardData.argtypes = [
            ctypes.c_uint,
            ctypes.c_void_p,
        ]
        user32.SetClipboardData.restype = ctypes.c_void_p

        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool

        handle = kernel32.GlobalAlloc(
            GMEM_MOVEABLE,
            len(data),
        )

        if not handle:
            raise RuntimeError(
                "GlobalAlloc() не выделил память."
            )

        clipboard_opened = False

        try:
            pointer = kernel32.GlobalLock(handle)

            if not pointer:
                raise RuntimeError(
                    "GlobalLock() не удался."
                )

            try:
                ctypes.memmove(
                    pointer,
                    data,
                    len(data),
                )

            finally:
                kernel32.GlobalUnlock(handle)

            if not user32.OpenClipboard(None):
                raise RuntimeError(
                    "OpenClipboard() не удался."
                )

            clipboard_opened = True

            if not user32.EmptyClipboard():
                raise RuntimeError(
                    "EmptyClipboard() не удался."
                )

            result = user32.SetClipboardData(
                CF_UNICODETEXT,
                handle,
            )

            if not result:
                raise RuntimeError(
                    "SetClipboardData() не удался."
                )

            # После успешного SetClipboardData Windows
            # становится владельцем handle.
            handle = None

        finally:
            if clipboard_opened:
                user32.CloseClipboard()

            if handle:
                kernel32.GlobalFree(handle)

    # ========================================================

    @classmethod
    def _paste(
        cls,
    ):
        # Ctrl down
        user32.keybd_event(
            VK_CONTROL,
            0,
            0,
            0,
        )

        # V down
        user32.keybd_event(
            VK_V,
            0,
            0,
            0,
        )

        # V up
        user32.keybd_event(
            VK_V,
            0,
            KEYEVENTF_KEYUP,
            0,
        )

        # Ctrl up
        user32.keybd_event(
            VK_CONTROL,
            0,
            KEYEVENTF_KEYUP,
            0,
        )


# ============================================================
# Тест
# ============================================================

if __name__ == "__main__":
    sender = GameChatSender()

    print(
        "Текущая точка:",
        sender.get_input_point(),
    )

    print()
    print(
        "Для теста сначала настройте game_chat.input_point "
        "в config.json."
    )
    print()

    text = input("Введите готовое сообщение для PoE: ").strip()

    if text:
        result = sender.send(text)

        print(
            "Результат:",
            "OK" if result else "ERROR",
        )
