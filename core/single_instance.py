from __future__ import annotations

import ctypes
from ctypes import wintypes


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\ExilingoSingleInstance"


class SingleInstance:
    """Windows named-mutex guard ensuring only one Exilingo instance runs."""

    def __init__(self, name: str = MUTEX_NAME):
        self.name = name
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self._kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        ]
        self._kernel32.CreateMutexW.restype = wintypes.HANDLE

        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

        ctypes.set_last_error(0)
        self.handle = self._kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            error = ctypes.get_last_error()
            raise OSError(error, "CreateMutexW failed", self.name)

        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS

    def release(self) -> None:
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "SingleInstance":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
