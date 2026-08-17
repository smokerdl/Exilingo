import os

# Автоматический импорт сигналов для PyQt6 или PySide6
try:
    from PyQt6.QtCore import QThread, pyqtSignal as Signal
except ImportError:
    try:
        from PySide6.QtCore import QThread, Signal
    except ImportError:
        raise ImportError("Для работы log_reader требуется PyQt6 или PySide6.")

from .log_parser import PoELogParser
from .models import ChatMessage


class LogReaderThread(QThread):
    """
    Фоновый поток для отслеживания обновлений в LatestClient.txt в реальном времени.
    """

    # Сигнал для передачи распарсенного сообщения чата в GUI
    new_chat_message = Signal(ChatMessage)

    # Сигнал изменения фокуса окна Path of Exile.
    # True  = [WINDOW] Gained focus
    # False = [WINDOW] Lost focus
    window_focus_changed = Signal(bool)

    # Сигнал текстового статуса
    status_changed = Signal(str)

    def __init__(
        self,
        log_filepath: str,
        read_from_end: bool = True,
        parent=None,
    ):
        super().__init__(parent)

        self.log_filepath = log_filepath
        self.read_from_end = read_from_end
        self.parser = PoELogParser()
        self._is_running = True

    def run(self):
        """Основной цикл отслеживания файла логов."""

        self.status_changed.emit(f"Поиск файла логов: {self.log_filepath}")

        # Ожидаем появления файла, если игра ещё не запущена
        while self._is_running and not os.path.exists(self.log_filepath):
            self.msleep(1000)

        if not self._is_running:
            return

        self.status_changed.emit("Файл логов найден. Открытие...")

        try:
            with open(
                self.log_filepath,
                "r",
                encoding="utf-8",
                errors="replace",
            ) as f:

                # Переходим в конец файла, чтобы читать только новые сообщения
                if self.read_from_end:
                    f.seek(0, os.SEEK_END)

                self.status_changed.emit("Мониторинг чата активен")

                while self._is_running:
                    line = f.readline()

                    if line:
                        stripped_line = line.strip()

                        if stripped_line.endswith("[WINDOW] Lost focus"):
                            self.window_focus_changed.emit(False)
                            continue

                        if stripped_line.endswith("[WINDOW] Gained focus"):
                            self.window_focus_changed.emit(True)
                            continue

                        entry = self.parser.parse_line(line)

                        if entry and entry.chat:
                            self.new_chat_message.emit(entry.chat)

                    else:
                        # Если лог был очищен или клиент перезаписал файл
                        current_pos = f.tell()

                        try:
                            if os.path.getsize(self.log_filepath) < current_pos:
                                f.seek(0)
                        except OSError:
                            pass

                        # Чтобы не нагружать процессор
                        self.msleep(100)

        except Exception as e:
            self.status_changed.emit(
                f"Ошибка чтения файла логов: {str(e)}"
            )

    def stop(self):
        """Плавная остановка потока."""

        self._is_running = False
        self.wait()


# Блок для независимого тестирования потока
if __name__ == "__main__":
    import sys

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    TEST_LOG_PATH = (
        r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\LatestClient.txt"
    )

    def handle_new_message(msg: ChatMessage):
        print(f"[{msg.channel.upper()}] {msg.sender}: {msg.text}")

    def handle_focus_changed(focused: bool):
        print(f"[WINDOW FOCUS] {'Gained' if focused else 'Lost'}")

    def handle_status(status: str):
        print(f"[STATUS] {status}")

    reader = LogReaderThread(
        log_filepath=TEST_LOG_PATH,
        read_from_end=False,
    )

    reader.new_chat_message.connect(handle_new_message)
    reader.window_focus_changed.connect(handle_focus_changed)
    reader.status_changed.connect(handle_status)

    reader.start()

    print("Поток запущен. Нажмите Ctrl+C в консоли для выхода.")

    sys.exit(app.exec())