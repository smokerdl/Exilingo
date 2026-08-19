from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\ExilingoSingleInstance"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.LPCWSTR,
]
kernel32.CreateMutexW.restype = wintypes.HANDLE

ctypes.set_last_error(0)
_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)

if not _handle:
    error = ctypes.get_last_error()
    raise OSError(error, "CreateMutexW failed", MUTEX_NAME)

if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(_handle)
    sys.exit(0)
