import sys
import os

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

        self.hotkey_listener.toggle_requested.connect(self.overlay.toggle_mode)

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

        self.translation_manager.translation_finished.connect(self.on_message_ready)

        self.translation_manager.translation_failed.connect(self.on_translation_failed)

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

        self.log_reader.new_chat_message.connect(self.on_new_chat_message)

        self.log_reader.status_changed.connect(self.on_log_status)

    # =======================================================
    # Верхняя панель Overlay
    # =======================================================

    def close_application(self):
        """Завершает работу программы."""

        print("[MAIN] Завершение работы...")

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

        Например:

            "hello"          -> Local
            "#hello"         -> Global
            "%hello"         -> Party
            "@Bob hello"     -> Whisper
            "$hello"         -> Trade
            "&hello"         -> Guild

        Далее сообщение проходит через TranslationManager
        с direction="outgoing".
        """

        text = str(text or "").strip()

        if not text:
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
            text,
            f"channel={channel}",
        )

        self.translation_manager.enqueue(MessageContext.from_chat_message(msg))

    # =======================================================
    # Translation Pipeline
    # =======================================================

    def on_message_ready(
        self,
        context: MessageContext,
    ):
        """
        Обрабатывает успешный результат TranslationManager.

        Incoming:
            сообщение отображается в Overlay.

        Outgoing:
            перевод отправляется в игровой чат через
            GameChatSender.

        ВАЖНО:

            Исходящее сообщение НЕ отображается напрямую
            в Overlay.

        После отправки в игру Path of Exile сама записывает
        сообщение в LatestClient.txt.

        Затем LogReader -> LogParser -> TranslationManager
        обрабатывают его как обычное входящее сообщение.

        Благодаря этому в Overlay появляется именно:

            Вася: Привет

        а не искусственное:

            You: Hello
        """

        print(
            "[MAIN] Сообщение готово:",
            context.display_text,
        )

        # ---------------------------------------------------
        # Определяем outgoing
        # ---------------------------------------------------

        is_outgoing = context.direction is not None and str(
            context.direction
        ).strip().lower() in {
            "outgoing",
            "out",
            "send",
            "sent",
            "to",
            "кому",
        }

        # ---------------------------------------------------
        # Outgoing
        # ---------------------------------------------------

        if is_outgoing:
            prepared_text = context.display_text or context.original_text

            print(
                "[MAIN] Отправка исходящего сообщения в игру:",
                prepared_text,
            )

            sent = self.game_chat_sender.send(
                prepared_text,
            )

            if not sent:
                print("[MAIN] Не удалось отправить исходящее сообщение в игру.")

            else:
                print("[MAIN] Исходящее сообщение передано игре.")

            # ------------------------------------------------
            # НИЧЕГО НЕ ДОБАВЛЯЕМ В OVERLAY.
            #
            # Сообщение должно появиться там только после
            # возврата из LatestClient.txt.
            # ------------------------------------------------

            return

        # ---------------------------------------------------
        # Incoming
        # ---------------------------------------------------

        sender = context.sender

        if context.guild_tag:
            sender = f"<{context.guild_tag}> {sender}"

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
        """
        Обрабатывает ситуацию, когда все провайдеры
        перевода завершились ошибкой.

        Incoming:
            оригинальное сообщение показывается в Overlay.

        Outgoing:
            оригинальное сообщение отправляется в игру.

        ВАЖНО:

            Outgoing также НЕ добавляется напрямую
            в Overlay.

        Если игра успешно отправит сообщение, оно позже
        вернётся через LatestClient.txt и будет обработано
        обычным incoming pipeline.
        """

        print(
            "[MAIN] Перевод не выполнен:",
            context.original_text,
            "|",
            error,
        )

        # ---------------------------------------------------
        # Определяем outgoing
        # ---------------------------------------------------

        is_outgoing = context.direction is not None and str(
            context.direction
        ).strip().lower() in {
            "outgoing",
            "out",
            "send",
            "sent",
            "to",
            "кому",
        }

        # ---------------------------------------------------
        # Outgoing
        # ---------------------------------------------------

        if is_outgoing:
            print(
                "[MAIN] Отправка оригинального исходящего сообщения в игру:",
                context.original_text,
            )

            sent = self.game_chat_sender.send(
                context.original_text,
            )

            if not sent:
                print("[MAIN] Не удалось отправить исходное сообщение в игру.")

            else:
                print("[MAIN] Исходное сообщение передано игре.")

            # ------------------------------------------------
            # НИЧЕГО НЕ ДОБАВЛЯЕМ В OVERLAY.
            # ------------------------------------------------

            return

        # ---------------------------------------------------
        # Incoming
        # ---------------------------------------------------

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

        sys.exit(ret)


if __name__ == "__main__":
    app = ExilingoApp()

    app.run()
