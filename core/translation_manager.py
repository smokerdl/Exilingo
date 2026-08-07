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

    # ======================================================
    # Константы локального определения языка
    # ======================================================

    MIN_LANGUAGE_LETTERS = 3

    # Минимальная доля символов одного алфавита,
    # чтобы считать сообщение однозначно написанным
    # на соответствующем языке.
    LANGUAGE_CONFIDENCE = 0.70

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
                    f"{context.original_text} "
                    f"-> {context.display_text}"
                )

                self.translation_finished.emit(context)

            except Exception as e:
                context.translation_success = False
                context.error = str(e)

                print(
                    "[TranslationManager] ERROR:",
                    e,
                )

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
        """
        Основной pipeline обработки сообщения.

        Перед отправкой текста переводчику выполняется
        локальная проверка языка.

        Если сообщение уже находится на целевом языке,
        API переводчика не вызывается.
        """

        # --------------------------------------------------
        # Исходный текст
        # --------------------------------------------------

        text = context.original_text.strip()

        # --------------------------------------------------
        # Нормализация
        # --------------------------------------------------

        normalized = self._normalize(text)

        context.normalized_text = normalized

        # --------------------------------------------------
        # Локальное определение:
        # нужно ли вообще переводить сообщение
        # --------------------------------------------------

        expected_source_language = self._expected_source_language(context)

        detected_language = self._detect_script_language(normalized)

        context.source_language = detected_language
        context.target_language = "en" if expected_source_language == "ru" else "ru"

        if self._should_skip_translation(
            detected_language,
            expected_source_language,
        ):
            context.translated_text = normalized
            context.display_text = normalized

            # Сообщение не переводилось.
            context.translation_success = False

            context.provider = None
            context.from_cache = False

            print(
                "[TranslationManager] "
                f"skip translation: "
                f"{normalized} "
                f"(detected={detected_language}, "
                f"expected={expected_source_language})"
            )

            return

        # --------------------------------------------------
        # Перевод
        # --------------------------------------------------

        translated = self.translator.translate(normalized)

        context.translated_text = translated
        context.display_text = translated

        # --------------------------------------------------
        # Успешный перевод
        # --------------------------------------------------

        context.translation_success = True

        # --------------------------------------------------
        # Информация о переводчике
        # --------------------------------------------------

        context.provider = self.translator.name

        if hasattr(
            self.translator,
            "source_lang",
        ):
            context.source_language = self.translator.source_lang

        if hasattr(
            self.translator,
            "target_lang",
        ):
            context.target_language = self.translator.target_lang

    # ======================================================
    # Определение ожидаемого исходного языка
    # ======================================================

    def _expected_source_language(
        self,
        context: MessageContext,
    ) -> str:
        """
        Определяет, на каком языке мы ожидаем
        исходный текст.

        Incoming / From:
            ожидаем EN.

        Outgoing / To:
            ожидаем RU.

        Для остальных сообщений предполагается
        входящий английский текст.
        """

        direction = (context.direction or "").strip().lower()

        if direction in (
            "to",
            "кому",
        ):
            return "ru"

        return "en"

    # ======================================================
    # Локальный детектор языка
    # ======================================================

    def _detect_script_language(
        self,
        text: str,
    ) -> Optional[str]:
        """
        Очень простой локальный детектор языка.

        Он не пытается определить язык по словарю.
        Вместо этого смотрит на алфавит:

            кириллица -> ru
            латиница  -> en

        Если букв слишком мало или текст смешанный,
        возвращается None.

        Это специально сделано консервативно:
        лучше отправить сомнительное сообщение
        на перевод, чем ошибочно пропустить его.
        """

        cyrillic_count = 0
        latin_count = 0

        for char in text:
            if self._is_cyrillic(char):
                cyrillic_count += 1

            elif self._is_latin(char):
                latin_count += 1

        total_letters = cyrillic_count + latin_count

        # Недостаточно информации.
        #
        # Например:
        #   "8L"
        #   "gg"
        #   "xd"
        #   "123"
        #
        # Такие сообщения не пытаемся классифицировать.
        if total_letters < self.MIN_LANGUAGE_LETTERS:
            return None

        cyrillic_ratio = cyrillic_count / total_letters

        latin_ratio = latin_count / total_letters

        if cyrillic_ratio >= self.LANGUAGE_CONFIDENCE:
            return "ru"

        if latin_ratio >= self.LANGUAGE_CONFIDENCE:
            return "en"

        # Смешанный текст.
        return None

    # ======================================================
    # Проверка символов
    # ======================================================

    @staticmethod
    def _is_cyrillic(
        char: str,
    ) -> bool:

        code = ord(char)

        return 0x0400 <= code <= 0x04FF

    # ------------------------------------------------------

    @staticmethod
    def _is_latin(
        char: str,
    ) -> bool:

        code = ord(char)

        return (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A)

    # ======================================================
    # Решение: пропускать перевод или нет
    # ======================================================

    def _should_skip_translation(
        self,
        detected_language: Optional[str],
        expected_source_language: str,
    ) -> bool:
        """
        Возвращает True, если сообщение уже находится
        на ожидаемом целевом языке и перевод не нужен.

        Например:

        Incoming:
            expected = en

            "Привет всем" -> detected ru
            => переводим? НЕТ.

        Outgoing:
            expected = ru

            "WTB mirror" -> detected en
            => переводим? НЕТ.

        Если язык не определён:
            => обычный перевод.
        """

        if detected_language is None:
            return False

        # Для входящего ожидаем английский.
        # Если обнаружена кириллица — сообщение уже
        # на русском и его переводить не надо.
        if expected_source_language == "en":
            return detected_language == "ru"

        # Для исходящего ожидаем русский.
        # Если обнаружена латиница — сообщение уже
        # на английском и его переводить не надо.
        if expected_source_language == "ru":
            return detected_language == "en"

        return False

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
    from providers.google_translate import (
        GoogleTranslateTranslator,
    )

    from .models import (
        ChatMessage,
        MessageContext,
    )

    manager = TranslationManager(
        GoogleTranslateTranslator(
            source_lang="en",
            target_lang="ru",
        )
    )

    def finished(
        context: MessageContext,
    ):

        print(f"[{context.provider}] {context.original_text}")

        print(" ↓ ")

        print(context.display_text)

        print()

    def failed(
        context: MessageContext,
        error: str,
    ):

        print(
            "Ошибка:",
            error,
        )

    manager.translation_finished.connect(finished)

    manager.translation_failed.connect(failed)

    manager.start()

    # --------------------------------------------------
    # Входящие
    # --------------------------------------------------

    test_messages = [
        # Должен переводиться.
        (
            "From",
            "Hello everyone",
        ),
        # Уже русский — перевод НЕ нужен.
        (
            "From",
            "Всем привет",
        ),
        # Должен переводиться.
        (
            "From",
            "WTB mirror",
        ),
        # Слишком короткий/неоднозначный —
        # отправляется переводчику.
        (
            "From",
            "gg",
        ),
        # ------------------------------------------------
        # Исходящие
        # ------------------------------------------------
        # Уже английский — перевод НЕ нужен.
        (
            "To",
            "Hello everyone",
        ),
        # Русский — должен переводиться.
        (
            "To",
            "Всем привет",
        ),
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
