from __future__ import annotations

import ctypes
import time
from typing import Optional, Tuple

from core.config_manager import config


# ============================================================
# Windows API
# ============================================================

user32 = ctypes.windll.user32

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
    Отвечает только за физическую отправку готового сообщения
    в игровой чат Path of Exile.

    Логика переводов, каналов и префиксов находится выше.

    Пример:

        sender.send("#hello everyone")

    В игровом чате будет введено:

        #hello everyone

    Класс:

    1. получает координаты точки игрового чата;
    2. перемещает курсор;
    3. кликает по полю чата;
    4. помещает текст в Clipboard;
    5. выполняет Ctrl+V;
    6. нажимает Enter.
    """

    # --------------------------------------------------------
    # Настройки по умолчанию
    # --------------------------------------------------------

    DEFAULT_CLICK_DELAY = 0.05
    DEFAULT_PASTE_DELAY = 0.05
    DEFAULT_ENTER_DELAY = 0.05

    # ========================================================
    # Конфигурация
    # ========================================================

    @staticmethod
    def get_input_point() -> Optional[Tuple[int, int]]:
        """
        Возвращает сохраненную точку активации игрового чата.

        Формат config.json:

            "game_chat": {
                "input_point": {
                    "x": 420,
                    "y": 970
                }
            }

        Если координаты не настроены, возвращает None.
        """

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

        return x, y

    # --------------------------------------------------------

    @staticmethod
    def set_input_point(
        x: int,
        y: int,
    ):
        """
        Сохраняет координату активации игрового чата.
        """

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
        """
        Отправляет готовый текст в игровой чат.

        Parameters
        ----------
        text:
            Полностью готовое сообщение.

            Например:

                "#hello"
                "$WTB Mageblood"
                "%hello party"
                "@PlayerName hello"

        point:
            Необязательная координата поля чата.

            Если не указана, используется координата
            из config.json.

        Returns
        -------
        bool
            True  — сообщение отправлено.
            False — отправка не выполнена.
        """

        if not text:
            print("[GameChatSender] Пустое сообщение.")

            return False

        text = text.strip()

        if not text:
            print("[GameChatSender] Сообщение состоит только из пробелов.")

            return False

        # ----------------------------------------------------
        # Координата
        # ----------------------------------------------------

        if point is None:
            point = self.get_input_point()

        if point is None:
            print("[GameChatSender] Координата игрового чата не настроена.")

            return False

        x, y = point

        # ----------------------------------------------------
        # Проверяем координаты
        # ----------------------------------------------------

        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)

        if not (0 <= x < screen_width and 0 <= y < screen_height):
            print(f"[GameChatSender] Некорректная координата: ({x}, {y})")

            return False

        # ----------------------------------------------------
        # Отправка
        # ----------------------------------------------------

        print(
            "[GameChatSender] Отправка в игровой чат:",
            text,
        )

        try:
            self._click(
                x,
                y,
            )

            time.sleep(
                self.DEFAULT_CLICK_DELAY,
            )

            self._paste_text(text)

            time.sleep(
                self.DEFAULT_PASTE_DELAY,
            )

            self._press_key(
                VK_RETURN,
            )

            time.sleep(
                self.DEFAULT_ENTER_DELAY,
            )

            print("[GameChatSender] Сообщение отправлено.")

            return True

        except Exception as e:
            print(
                "[GameChatSender] Ошибка отправки:",
                e,
            )

            return False

    # ========================================================
    # Mouse
    # ========================================================

    @staticmethod
    def _click(
        x: int,
        y: int,
    ):
        """
        Перемещает курсор в указанную точку
        и выполняет левый клик.
        """

        if not user32.SetCursorPos(
            int(x),
            int(y),
        ):
            raise RuntimeError("Не удалось переместить курсор.")

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
        """
        Нажимает и отпускает виртуальную клавишу.
        """

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

        Используется WinAPI, поэтому дополнительная библиотека
        для Clipboard не требуется.
        """

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        # +1 для завершающего \0
        data = (text + "\0").encode(
            "utf-16-le",
        )

        kernel32 = ctypes.windll.kernel32

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

        kernel32.GlobalFree.argtypes = [
            ctypes.c_void_p,
        ]

        handle = kernel32.GlobalAlloc(
            GMEM_MOVEABLE,
            len(data),
        )

        if not handle:
            raise RuntimeError("GlobalAlloc() не выделил память.")

        try:
            pointer = kernel32.GlobalLock(
                handle,
            )

            if not pointer:
                raise RuntimeError("GlobalLock() не удался.")

            try:
                ctypes.memmove(
                    pointer,
                    data,
                    len(data),
                )

            finally:
                kernel32.GlobalUnlock(
                    handle,
                )

            if not user32.OpenClipboard(
                None,
            ):
                raise RuntimeError("Не удалось открыть Clipboard.")

            try:
                if not user32.EmptyClipboard():
                    raise RuntimeError("Не удалось очистить Clipboard.")

                if not user32.SetClipboardData(
                    CF_UNICODETEXT,
                    handle,
                ):
                    raise RuntimeError("Не удалось установить Clipboard.")

                # После успешного SetClipboardData
                # Windows становится владельцем handle.
                handle = None

            finally:
                user32.CloseClipboard()

        finally:
            if handle:
                kernel32.GlobalFree(
                    handle,
                )

    # ========================================================

    @classmethod
    def _paste_text(
        cls,
        text: str,
    ):
        """
        Помещает текст в Clipboard и выполняет Ctrl+V.
        """

        cls._set_clipboard_text(
            text,
        )

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
    print("Для теста сначала настройте game_chat.input_point в config.json.")
    print()

    text = input("Введите готовое сообщение для PoE: ").strip()

    if text:
        result = sender.send(
            text,
        )

        print(
            "Результат:",
            "OK" if result else "ERROR",
        )
