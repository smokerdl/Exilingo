import sys
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.log_reader import LogReaderThread
from core.log_parser import ChatMessage
from core.models import MessageContext
from core.translation_manager import TranslationManager
from core.translation_router import TranslationRouter
from core.config_manager import config
from core.provider_registry import ProviderRegistry
from core.game_chat_sender import GameChatSender

from ui.chat_overlay import ChatOverlay, GlobalHotkeyListener
from ui.settings_dialog import SettingsDialog


# Стандартные пути к логам PoE (Standalone и Steam)
DEFAULT_LOG_PATHS = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\LatestClient.txt",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"D:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
    r"E:\SteamLibrary\steamapps\common\Path of Exile\logs\LatestClient.txt",
]


# ============================================================
# Игровые каналы исходящих сообщений
# ============================================================

OUTGOING_CHANNELS = {
    "": ("local", ""),
    "#": ("global", "#"),
    "%": ("party", "%"),
    "@": ("whisper", "@"),
    "$": ("trade", "$"),
    "&": ("guild", "&"),
}


# ============================================================
# F5 — отправка сообщения без переключения режима Overlay
# ============================================================

class OutgoingHotkeyListener(QObject):
    """
    Отдельный глобальный слушатель F5.

    Enter остаётся полностью за GlobalHotkeyListener и
    переключает режим Overlay.

    F5 только инициирует отправку текущего текста из Overlay
    и никогда не меняет режим click-through.
    """

    send_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self._keyboard = None

        try:
            import keyboard

            self._keyboard = keyboard

            keyboard.add_hotkey(
                "f5",
                self._on_f5,
            )

            print(
                "[Hotkey] F5 зарегистрирована: отправка сообщения."
            )

        except Exception as e:
            print(
                f"[HotkeyError] Не удалось зарегистрировать F5: {e}"
            )

    def _on_f5(self):
        print("[Hotkey] F5 нажата -> запрос отправки сообщения.")
        self.send_requested.emit()

    def stop(self):
        if self._keyboard is None:
            return

        try:
            self._keyboard.remove_hotkey("f5")
        except Exception as e:
            print(f"[HotkeyError] Не удалось снять F5: {e}")


class ExilingoApp:
    def __init__(self):

        self.app = QApplication(sys.argv)

        # ---------------------------------------------------
        # Overlay
        # ---------------------------------------------------

        self.overlay = ChatOverlay()

        self.overlay.close_requested.connect(self.close_application)

        self.overlay.settings_requested.connect(self.open_settings)

        # Исходящие сообщения из поля ввода Overlay.
        self.overlay.send_message_requested.connect(self.on_outgoing_message)

        # ---------------------------------------------------
        # Hotkey
        # ---------------------------------------------------

        self.hotkey_listener = GlobalHotkeyListener()

        # Enter = только переключение режима Overlay.
        self.hotkey_listener.toggle_requested.connect(
            self.overlay.toggle_mode
        )

        # F5 = только отправка текущего сообщения.
        # Режим Overlay при этом НЕ меняется.
        self.outgoing_hotkey_listener = OutgoingHotkeyListener()

        self.outgoing_hotkey_listener.send_requested.connect(
            self.overlay._on_send
        )

        # ---------------------------------------------------
        # Provider Registry + Router
        # ---------------------------------------------------

        self.provider_registry = ProviderRegistry()
        self.translation_router = TranslationRouter()

        # ---------------------------------------------------
        # Translation Manager
        # ---------------------------------------------------

        self.translation_manager = TranslationManager(
            registry=self.provider_registry,
            router=self.translation_router,
        )

        self.translation_manager.translation_finished.connect(
            self.on_message_ready
        )

        self.translation_manager.translation_failed.connect(
            self.on_translation_failed
        )

        self.translation_manager.start()

        # ---------------------------------------------------
        # Game Chat Sender
        # ---------------------------------------------------

        self.game_chat_sender = GameChatSender()

        # ---------------------------------------------------
        # Log Reader
        # ---------------------------------------------------

        log_path = config.log_path

        if not log_path:
            for path in DEFAULT_LOG_PATHS:
                if os.path.exists(path):
                    log_path = path
                    break

            if not log_path:
                log_path = DEFAULT_LOG_PATHS[0]

            config.log_path = log_path

        print(f"[Main] Используется путь к логу: {log_path}")

        self.log_reader = LogReaderThread(
            log_filepath=log_path,
            read_from_end=True,
        )

        self.log_reader.new_chat_message.connect(
            self.on_new_chat_message
        )

        self.log_reader.status_changed.connect(
            self.on_log_status
        )

    # =======================================================
    # Верхняя панель Overlay
    # =======================================================

    def close_application(self):
        """Завершает работу программы."""

        print("[MAIN] Завершение работы...")

        try:
            self.outgoing_hotkey_listener.stop()
        except Exception:
            pass

        self.app.quit()

    # -------------------------------------------------------

    def open_settings(self):
        """Открывает полноценное окно настроек Exilingo."""

        print("[MAIN] Открытие окна настроек")

        accepted = SettingsDialog.open_settings(
            self.overlay,
        )

        if accepted:
            print("[MAIN] Настройки сохранены")
        else:
            print("[MAIN] Настройки отменены")

    # =======================================================
    # Log Reader
    # =======================================================

    def on_new_chat_message(
        self,
        msg: ChatMessage,
    ):

        print(
            "[MAIN] Получено сообщение:",
            msg.text,
        )

        context = MessageContext.from_chat_message(msg)

        self.translation_manager.enqueue(context)

    # =======================================================
    # Outgoing Overlay -> TranslationManager
    # =======================================================

    def on_outgoing_message(
        self,
        text: str,
    ):
        """
        Получает сообщение из поля ввода Overlay.

        Overlay уже добавляет игровой prefix, если пользователь
        не указал его самостоятельно.
        """

        text = str(text or "").strip()

        if not text:
            print("[MAIN] Пустое исходящее сообщение — игнорируем.")
            return

        prefix = text[0] if text[0] in OUTGOING_CHANNELS else ""

        channel, channel_symbol = OUTGOING_CHANNELS.get(
            prefix,
            ("local", ""),
        )

        msg = ChatMessage(
            channel=channel,
            channel_symbol=channel_symbol,
            sender="You",
            text=text,
            direction="outgoing",
        )

        print(
            "[MAIN] Исходящее сообщение из Overlay:",
            repr(text),
            f"channel={channel}",
            f"prefix={prefix!r}",
        )

        self.translation_manager.enqueue(
            MessageContext.from_chat_message(msg)
        )

    # =======================================================
    # Translation Pipeline
    # =======================================================

    def on_message_ready(
        self,
        context: MessageContext,
    ):
        """
        Incoming:
            сообщение отображается в Overlay.

        Outgoing:
            перевод отправляется в игровой чат через
            GameChatSender.

        Outgoing НЕ отображается напрямую в Overlay.
        После отправки PoE должна записать сообщение в
        LatestClient.txt, после чего оно вернётся через
        обычный LogReader -> LogParser -> TranslationManager.
        """

        print(
            "[MAIN] Сообщение готово:",
            repr(context.display_text),
            f"provider={context.provider!r}",
            f"direction={context.direction!r}",
        )

        is_outgoing = (
            context.direction is not None
            and str(context.direction).strip().lower()
            in {
                "outgoing",
                "out",
                "send",
                "sent",
                "to",
                "кому",
            }
        )

        # ---------------------------------------------------
        # Outgoing
        # ---------------------------------------------------

        if is_outgoing:

            prepared_text = (
                context.display_text
                or context.original_text
            )

            print(
                "[MAIN] OUTGOING -> GameChatSender.send():",
                repr(prepared_text),
            )

            sent = self.game_chat_sender.send(
                prepared_text,
            )

            if not sent:
                print(
                    "[MAIN] OUTGOING FAILED: GameChatSender вернул False."
                )
            else:
                print(
                    "[MAIN] OUTGOING OK: сообщение передано GameChatSender."
                )

            # Никогда не рисуем outgoing напрямую.
            return

        # ---------------------------------------------------
        # Incoming
        # ---------------------------------------------------

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

        print(
            "[MAIN] INCOMING -> Overlay.add_message():",
            f"sender={sender!r}",
            f"text={context.display_text!r}",
        )

        self.overlay.add_message(
            channel_prefix=context.channel_symbol,
            sender=sender,
            text=context.display_text,
            is_translated=context.translation_success,
        )

    # -------------------------------------------------------

    def on_translation_failed(
        self,
        context: MessageContext,
        error: str,
    ):
        """Обрабатывает ситуацию, когда все провайдеры перевода завершились ошибкой."""

        print(
            "[MAIN] Перевод не выполнен:",
            repr(context.original_text),
            "|",
            error,
            f"direction={context.direction!r}",
        )

        is_outgoing = (
            context.direction is not None
            and str(context.direction).strip().lower()
            in {
                "outgoing",
                "out",
                "send",
                "sent",
                "to",
                "кому",
            }
        )

        if is_outgoing:

            print(
                "[MAIN] OUTGOING FALLBACK -> GameChatSender.send():",
                repr(context.original_text),
            )

            sent = self.game_chat_sender.send(
                context.original_text,
            )

            if not sent:
                print(
                    "[MAIN] OUTGOING FALLBACK FAILED."
                )
            else:
                print(
                    "[MAIN] OUTGOING FALLBACK OK."
                )

            # Не рисуем outgoing напрямую.
            return

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

        self.overlay.add_message(
            channel_prefix=context.channel_symbol,
            sender=sender,
            text=context.original_text,
            is_translated=False,
        )

    # =======================================================

    def on_log_status(
        self,
        status: str,
    ):

        print(f"[LogReader] {status}")

    # =======================================================

    def run(self):

        self.log_reader.start()

        self.overlay.show()

        self.overlay.add_message(
            "",
            "Exilingo",
            "Translation Pipeline готов.",
            is_translated=True,
        )

        ret = self.app.exec()

        self.log_reader.stop()
        self.translation_manager.stop()

        try:
            self.outgoing_hotkey_listener.stop()
        except Exception:
            pass

        sys.exit(ret)


if __name__ == "__main__":
    app = ExilingoApp()

    app.run()

