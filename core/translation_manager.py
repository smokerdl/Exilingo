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
    """Центральный диспетчер переводов."""

    translation_finished = Signal(MessageContext)
    translation_failed = Signal(MessageContext, str)
    queue_size_changed = Signal(int)
    worker_started = Signal()
    worker_stopped = Signal()

    # Сообщения с меньшим количеством букв не классифицируем.
    MIN_LANGUAGE_LETTERS = 3

    def __init__(self, translator: BaseTranslator):
        super().__init__()
        self.translator = translator
        self._queue: queue.Queue[Optional[MessageContext]] = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

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

    def enqueue(self, context: MessageContext):
        print(f"[TranslationManager] enqueue: {context.original_text}")
        self._queue.put(context)
        self.queue_size_changed.emit(self._queue.qsize())

    def pending_count(self) -> int:
        return self._queue.qsize()

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
                self.translation_failed.emit(context, str(e))

    def _process_context(self, context: MessageContext):
        text = context.original_text.strip()
        normalized = self._normalize(text)
        context.normalized_text = normalized

        expected_source_language = self._expected_source_language(context)
        detected_language = self._detect_script_language(normalized)

        context.source_language = detected_language
        context.target_language = (
            "en" if expected_source_language == "ru" else "ru"
        )

        if self._should_skip_translation(
            detected_language,
            expected_source_language,
        ):
            context.translated_text = normalized
            context.display_text = normalized
            context.translation_success = False
            context.provider = None
            context.from_cache = False

            print(
                "[TranslationManager] skip translation: "
                f"{normalized} "
                f"(detected={detected_language}, "
                f"expected={expected_source_language})"
            )
            return

        translated = self.translator.translate(normalized)
        context.translated_text = translated
        context.display_text = translated
        context.translation_success = True
        context.provider = self.translator.name

        if hasattr(self.translator, "source_lang"):
            context.source_language = self.translator.source_lang
        if hasattr(self.translator, "target_lang"):
            context.target_language = self.translator.target_lang

    def _expected_source_language(self, context: MessageContext) -> str:
        """Определяет ожидаемый язык исходного текста."""
        direction = (context.direction or "").strip().lower()
        if direction in ("to", "кому"):
            return "ru"
        return "en"

    def _detect_script_language(self, text: str) -> Optional[str]:
        """
        Локально определяет язык только по алфавиту.

        Возвращает:
          ru   — есть кириллица и нет латиницы;
          en   — есть латиница и нет кириллицы;
          None — смешанный текст или слишком мало букв.

        Ключевой момент: процентное соотношение букв больше
        не используется. Даже одна латинская буква в кириллическом
        сообщении делает его смешанным и отправляет его на перевод.
        """
        cyrillic_count = 0
        latin_count = 0

        for char in text:
            if self._is_cyrillic(char):
                cyrillic_count += 1
            elif self._is_latin(char):
                latin_count += 1

        total_letters = cyrillic_count + latin_count

        if total_letters < self.MIN_LANGUAGE_LETTERS:
            return None

        # Смешанный текст всегда переводим.
        if cyrillic_count > 0 and latin_count > 0:
            return None

        if cyrillic_count > 0:
            return "ru"

        if latin_count > 0:
            return "en"

        return None

    @staticmethod
    def _is_cyrillic(char: str) -> bool:
        code = ord(char)
        return 0x0400 <= code <= 0x04FF

    @staticmethod
    def _is_latin(char: str) -> bool:
        code = ord(char)
        return (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A)

    def _should_skip_translation(
        self,
        detected_language: Optional[str],
        expected_source_language: str,
    ) -> bool:
        """
        Пропускаем перевод только для полностью одноязычного текста
        на языке, который является целевым для данного направления.

        Incoming (ожидаем EN): полностью кириллическое сообщение
        уже русское -> пропускаем.

        Outgoing (ожидаем RU): полностью латинское сообщение
        уже английское -> пропускаем.

        Смешанные сообщения никогда не пропускаются.
        """
        if detected_language is None:
            return False

        if expected_source_language == "en":
            return detected_language == "ru"

        if expected_source_language == "ru":
            return detected_language == "en"

        return False

    def _normalize(self, text: str) -> str:
        text = text.strip()
        text = " ".join(text.split())
        return text

    def set_translator(self, translator: BaseTranslator):
        self.translator = translator


if __name__ == "__main__":
    from providers.google_translate import GoogleTranslateTranslator
    from .models import ChatMessage, MessageContext

    manager = TranslationManager(
        GoogleTranslateTranslator(source_lang="en", target_lang="ru")
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

    test_messages = [
        ("From", "Hello everyone"),
        ("From", "Всем привет"),
        ("From", "WTB mirror"),
        ("From", "gg"),
        ("From", "Бальзамировщик, Перчатки крови IS THIS GOOD?"),
        ("To", "Hello everyone"),
        ("To", "Всем привет"),
        ("To", "Привет guys, WTB mirror"),
    ]

    for direction, text in test_messages:
        msg = ChatMessage(
            channel="whisper",
            channel_symbol="@",
            sender="Tester",
            text=text,
            direction=direction,
        )
        manager.enqueue(MessageContext.from_chat_message(msg))

    while manager.pending_count():
        time.sleep(0.1)

    time.sleep(0.5)
    manager.stop()
