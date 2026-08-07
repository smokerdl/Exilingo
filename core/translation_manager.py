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
from .provider_registry import ProviderRegistry
from .translation_router import TranslationRouter


class TranslationManager(QObject):
    """
    Центральный диспетчер переводов.

    Pipeline:

        MessageContext
            ↓
        TranslationRouter
            ↓
        очередь провайдеров
            ↓
        ProviderRegistry
            ↓
        первый успешно отработавший провайдер
            ↓
        Overlay

    Если первый провайдер маршрута недоступен или завершился
    ошибкой, менеджер пробует следующий провайдер.
    """

    translation_finished = Signal(MessageContext)
    translation_failed = Signal(MessageContext, str)

    queue_size_changed = Signal(int)

    worker_started = Signal()
    worker_stopped = Signal()

    # Сообщения с меньшим количеством букв не классифицируем.
    MIN_LANGUAGE_LETTERS = 3

    def __init__(
        self,
        translator: Optional[BaseTranslator] = None,
        registry: Optional[ProviderRegistry] = None,
        router: Optional[TranslationRouter] = None,
    ):
        super().__init__()

        # --------------------------------------------------
        # Новый routing-based pipeline
        # --------------------------------------------------

        self.registry = registry or ProviderRegistry()
        self.router = router or TranslationRouter()

        # --------------------------------------------------
        # Совместимость со старым кодом
        # --------------------------------------------------
        #
        # Если передан translator, он используется только
        # как fallback старого API. Основной main.py теперь
        # работает через registry + router.
        #
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
        print(
            f"[TranslationManager] enqueue: "
            f"{context.original_text}"
        )

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
        # --------------------------------------------------
        # Нормализация
        # --------------------------------------------------

        text = context.original_text.strip()
        normalized = self._normalize(text)
        context.normalized_text = normalized

        # --------------------------------------------------
        # Routing
        # --------------------------------------------------

        decision = self.router.resolve(context)

        expected_source_language = decision.source_language or (
            "ru" if decision.direction == "outgoing" else "en"
        )

        expected_target_language = decision.target_language or (
            "en" if decision.direction == "outgoing" else "ru"
        )

        # --------------------------------------------------
        # Локальная проверка языка
        # --------------------------------------------------

        detected_language = self._detect_script_language(normalized)

        context.source_language = detected_language or expected_source_language
        context.target_language = expected_target_language

        # Если сообщение уже на целевом языке — не отправляем
        # его ни одному внешнему провайдеру.
        if self._should_skip_translation(
            detected_language,
            expected_source_language,
        ):
            context.translated_text = normalized
            context.display_text = normalized
            context.translation_success = False
            context.provider = None
            context.from_cache = False
            context.error = None

            print(
                "[TranslationManager] skip translation: "
                f"{normalized} "
                f"(detected={detected_language}, "
                f"expected={expected_source_language})"
            )

            return

        # --------------------------------------------------
        # Очередь провайдеров
        # --------------------------------------------------

        errors = []

        for provider_id in decision.providers:
            try:
                if not self.registry.is_available(provider_id):
                    errors.append(
                        f"{provider_id}: недоступен или выключен"
                    )
                    continue

                translator = self.registry.create(
                    provider_id,
                    source_language=expected_source_language,
                    target_language=expected_target_language,
                )

                print(
                    "[TranslationManager] trying provider:",
                    provider_id,
                    f"({expected_source_language}->{expected_target_language})",
                )

                translated = translator.translate(
                    normalized,
                )

                if translated is None:
                    raise RuntimeError("Провайдер вернул None")

                translated = str(translated).strip()

                if not translated:
                    raise RuntimeError("Провайдер вернул пустой перевод")

                # ------------------------------------------
                # Успех
                # ------------------------------------------

                context.translated_text = translated
                context.display_text = translated
                context.translation_success = True
                context.provider = translator.name
                context.from_cache = False
                context.error = None

                # Фактическое направление провайдера.
                context.source_language = getattr(
                    translator,
                    "source_language",
                    getattr(
                        translator,
                        "source_lang",
                        expected_source_language,
                    ),
                )

                context.target_language = getattr(
                    translator,
                    "target_language",
                    getattr(
                        translator,
                        "target_lang",
                        expected_target_language,
                    ),
                )

                return

            except Exception as e:
                error_text = str(e)

                errors.append(
                    f"{provider_id}: {error_text}"
                )

                print(
                    f"[TranslationManager] provider '{provider_id}' failed: "
                    f"{error_text}"
                )

        # --------------------------------------------------
        # Старый translator как последний fallback
        # --------------------------------------------------

        if self.translator is not None:
            try:
                print(
                    "[TranslationManager] trying legacy translator fallback"
                )

                translated = self.translator.translate(normalized)

                if translated is None:
                    raise RuntimeError("Провайдер вернул None")

                translated = str(translated).strip()

                if not translated:
                    raise RuntimeError("Провайдер вернул пустой перевод")

                context.translated_text = translated
                context.display_text = translated
                context.translation_success = True
                context.provider = self.translator.name
                context.from_cache = False
                context.error = None

                context.source_language = getattr(
                    self.translator,
                    "source_language",
                    getattr(
                        self.translator,
                        "source_lang",
                        expected_source_language,
                    ),
                )

                context.target_language = getattr(
                    self.translator,
                    "target_language",
                    getattr(
                        self.translator,
                        "target_lang",
                        expected_target_language,
                    ),
                )

                return

            except Exception as e:
                errors.append(
                    f"legacy: {e}"
                )

        # --------------------------------------------------
        # Все провайдеры закончились
        # --------------------------------------------------

        raise RuntimeError(
            "Все провайдеры маршрута завершились ошибкой: "
            + "; ".join(errors)
        )

    # ======================================================
    # Язык
    # ======================================================

    def _detect_script_language(
        self,
        text: str,
    ) -> Optional[str]:
        """
        Локально определяет язык по алфавиту.

        ru:
            есть кириллица и нет латиницы.

        en:
            есть латиница и нет кириллицы.

        None:
            смешанный текст или слишком мало букв.

        Смешанные сообщения всегда отправляются на перевод.
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
        return (
            (0x0041 <= code <= 0x005A)
            or (0x0061 <= code <= 0x007A)
        )

    def _should_skip_translation(
        self,
        detected_language: Optional[str],
        expected_source_language: str,
    ) -> bool:
        """
        Пропускаем только сообщение, которое полностью написано
        на целевом языке текущего направления.

        Incoming:
            expected EN -> RU
            полностью RU -> skip

        Outgoing:
            expected RU -> EN
            полностью EN -> skip

        Смешанный текст никогда не пропускается.
        """
        if detected_language is None:
            return False

        if expected_source_language == "en":
            return detected_language == "ru"

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
    # Смена legacy-переводчика
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
    from .models import ChatMessage

    manager = TranslationManager(
        translator=GoogleTranslateTranslator(
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
        manager.enqueue(
            MessageContext.from_chat_message(msg)
        )

    while manager.pending_count():
        time.sleep(0.1)

    time.sleep(0.5)
    manager.stop()
