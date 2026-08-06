import queue
import threading
import time
from typing import Optional

try:
    from PyQt6.QtCore import QObject, pyqtSignal as Signal
except ImportError:
    from PySide6.QtCore import QObject, Signal

from providers.base import BaseTranslator

from .models import MessageContext


class TranslationManager(QObject):
    """
    Центральный диспетчер переводов.

    Работает с любым переводчиком,
    реализующим интерфейс BaseTranslator.
    """

    translation_finished = Signal(MessageContext)
    translation_failed = Signal(MessageContext, str)

    queue_size_changed = Signal(int)

    worker_started = Signal()
    worker_stopped = Signal()

    def __init__(self, translator: BaseTranslator):
        super().__init__()

        self.translator = translator

        self._queue: queue.Queue[Optional[MessageContext]] = queue.Queue()

        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ======================================================
    # Управление жизненным циклом
    # ======================================================

    def start(self):

        if self._running:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="TranslationWorker",
        )

        self._thread.start()

        self.worker_started.emit()

    def stop(self):

        if not self._running:
            return

        self._running = False

        self._queue.put(None)

        if self._thread is not None:
            self._thread.join(timeout=2)

        self.worker_stopped.emit()

    # ======================================================
    # Очередь
    # ======================================================

    def enqueue(self, context: MessageContext):

        print(f"[TranslationManager] enqueue: {context.original_text}")

        self._queue.put(context)

        self.queue_size_changed.emit(self._queue.qsize())

    def pending_count(self) -> int:

        return self._queue.qsize()

    # ======================================================
    # Worker
    # ======================================================

    def _worker_loop(self):

        while self._running:
            context = self._queue.get()

            if context is None:
                break

            self.queue_size_changed.emit(self._queue.qsize())

            try:
                self._process_context(context)

                print(
                    f"[TranslationManager] translated: "
                    f"{context.original_text} -> {context.display_text}"
                )

                self.translation_finished.emit(context)

            except Exception as e:
                context.translation_success = False
                context.error = str(e)

                print("[TranslationManager] ERROR:", e)

                self.translation_failed.emit(
                    context,
                    str(e),
                )

    # ======================================================
    # Pipeline
    # ======================================================

    def _process_context(
        self,
        context: MessageContext,
    ):

        # Исходный текст
        text = context.original_text.strip()

        # Нормализация
        normalized = self._normalize(text)
        context.normalized_text = normalized

        # Перевод
        translated = self.translator.translate(normalized)

        context.translated_text = translated
        context.display_text = translated

        # Успешный перевод
        context.translation_success = True

        # Информация о переводчике
        context.provider = self.translator.name

        if hasattr(self.translator, "source_lang"):
            context.source_language = self.translator.source_lang

        if hasattr(self.translator, "target_lang"):
            context.target_language = self.translator.target_lang

    # ======================================================
    # Нормализация
    # ======================================================

    def _normalize(
        self,
        text: str,
    ) -> str:

        text = text.strip()

        text = " ".join(text.split())

        return text

    # ======================================================
    # Смена переводчика
    # ======================================================

    def set_translator(
        self,
        translator: BaseTranslator,
    ):

        self.translator = translator


# ==========================================================
# Тестирование
# ==========================================================

if __name__ == "__main__":
    from providers.google_translate import GoogleTranslateTranslator
    from .models import ChatMessage, MessageContext

    manager = TranslationManager(
        GoogleTranslateTranslator(
            source_lang="en",
            target_lang="ru",
        )
    )

    def finished(context: MessageContext):

        print(f"[{context.provider}] {context.original_text}")
        print(" ↓ ")
        print(context.display_text)
        print()

    def failed(context: MessageContext, error: str):

        print("Ошибка:", error)

    manager.translation_finished.connect(finished)
    manager.translation_failed.connect(failed)

    manager.start()

    for text in [
        "WTB mirror",
        "selling mageblood",
        "ty",
    ]:
        msg = ChatMessage(
            channel="global",
            channel_symbol="#",
            sender="Tester",
            text=text,
        )

        manager.enqueue(MessageContext.from_chat_message(msg))

    while manager.pending_count():
        time.sleep(0.1)

    time.sleep(0.5)

    manager.stop()
