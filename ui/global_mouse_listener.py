from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from PyQt6.QtCore import QObject, pyqtSignal


class GlobalMouseListener(QObject):
    """Listen for global left mouse button presses on Windows."""

    left_click = pyqtSignal(int, int)

    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201
    WM_QUIT = 0x0012

    def __init__(self):
        super().__init__()
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._hook = None
        self._thread = None
        self._thread_id = None
        self._callback = None
        self._stop_event = threading.Event()

        # Explicit WinAPI signatures are important on 64-bit Python.
        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._user32.SetWindowsHookExW.restype = ctypes.c_void_p
        self._user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        self._user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32.CallNextHookEx.restype = wintypes.LRESULT if hasattr(wintypes, "LRESULT") else ctypes.c_ssize_t
        self._user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            ctypes.c_void_p,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._user32.GetMessageW.restype = wintypes.BOOL

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_hook,
            name="ExilingoGlobalMouseHook",
            daemon=True,
        )
        self._thread.start()

    def _run_hook(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()

        LowLevelMouseProc = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt", wintypes.POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        @LowLevelMouseProc
        def callback(n_code, w_param, l_param):
            if n_code >= 0 and w_param == self.WM_LBUTTONDOWN:
                data = ctypes.cast(
                    l_param, ctypes.POINTER(MSLLHOOKSTRUCT)
                ).contents
                x = int(data.pt.x)
                y = int(data.pt.y)

                # Diagnostic output is intentionally produced directly from
                # the hook thread. This tells us whether Windows actually
                # reaches the low-level mouse callback, independently of Qt's
                # cross-thread signal delivery.
                print(
                    f"[GlobalMouseHook] LMB x={x} y={y} "
                    f"thread={threading.get_ident()}",
                    flush=True,
                )
                self.left_click.emit(x, y)

            return self._user32.CallNextHookEx(
                self._hook, n_code, w_param, l_param
            )

        self._callback = callback
        module_handle = self._kernel32.GetModuleHandleW(None)
        self._hook = self._user32.SetWindowsHookExW(
            self.WH_MOUSE_LL, self._callback, module_handle, 0
        )

        if not self._hook:
            error = self._kernel32.GetLastError()
            print(
                f"[GlobalMouseHook] SetWindowsHookExW FAILED error={error}",
                flush=True,
            )
            self._callback = None
            self._thread_id = None
            return

        print(
            f"[GlobalMouseHook] installed hook={hex(int(self._hook))} "
            f"thread={self._thread_id}",
            flush=True,
        )

        msg = wintypes.MSG()
        while not self._stop_event.is_set():
            result = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break

        if self._hook:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._callback = None
        self._thread_id = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._callback = None
