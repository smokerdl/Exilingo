from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


CONFIG_FILE = "config.json"


# ==========================================================
# Значения конфигурации по умолчанию
# ==========================================================

DEFAULT_CONFIG = {
    # ------------------------------------------------------
    # Общие настройки
    # ------------------------------------------------------
    "general": {
        "log_path": "",
    },
    # ------------------------------------------------------
    # Overlay
    # ------------------------------------------------------
    "overlay": {
        "geometry": {
            "x": 1,
            "y": 11,
            "w": 700,
            "h": 309,
        },
        "font_size": 13,
    },
    # ------------------------------------------------------
    # Переводчики
    # ------------------------------------------------------
    "providers": {
        # --------------------------------------------------
        # Google Translate
        # --------------------------------------------------
        "google": {
            "enabled": True,
            # Языки для ВХОДЯЩИХ сообщений.
            #
            # Исходящие автоматически используют
            # обратное направление:
            #
            # incoming: en -> ru
            # outgoing: ru -> en
            #
            "source_language": "en",
            "target_language": "ru",
        },
        # --------------------------------------------------
        # Gemini
        # --------------------------------------------------
        "gemini": {
            "enabled": False,
            "api_key": "",
            "model": "gemini-2.5-flash",
            "system_prompt": (
                "You are a translator of the Path of Exile game chat. "
                "Translate naturally without explanations."
            ),
            # Языки входящих сообщений.
            "source_language": "en",
            "target_language": "ru",
        },
        # --------------------------------------------------
        # Groq
        # --------------------------------------------------
        "groq": {
            "enabled": False,
            "api_key": "",
            "model": "",
            "system_prompt": "",
            "source_language": "en",
            "target_language": "ru",
        },
        # --------------------------------------------------
        # OpenRouter
        # --------------------------------------------------
        "openrouter": {
            "enabled": False,
            "api_key": "",
            "model": "",
            "system_prompt": "",
            "source_language": "en",
            "target_language": "ru",
        },
        # --------------------------------------------------
        # Ollama
        # --------------------------------------------------
        "ollama": {
            "enabled": False,
            "host": "http://127.0.0.1:11434",
            "model": "",
            "system_prompt": "",
            "source_language": "en",
            "target_language": "ru",
        },
    },
    # ------------------------------------------------------
    # Маршрутизация
    # ------------------------------------------------------
    #
    # В каждом канале находится ОЧЕРЕДЬ провайдеров.
    #
    # Например:
    #
    # "whisper": [
    #     "gemini",
    #     "openrouter",
    #     "google",
    # ]
    #
    # TranslationRouter в будущем будет пробовать
    # провайдеров именно в указанном порядке.
    #
    # Пока доступен только Google Translate.
    # ------------------------------------------------------
    "routing": {
        "global": [
            "google",
        ],
        "local": [
            "google",
        ],
        "trade": [
            "google",
        ],
        "party": [
            "google",
        ],
        "guild": [
            "google",
        ],
        "whisper": [
            "google",
        ],
        # Outgoing использует тот же маршрут,
        # что и Whisper.
        #
        # Отдельная настройка в GUI для него
        # не нужна.
        "outgoing": [
            "google",
        ],
    },
}


# ==========================================================
# ConfigManager
# ==========================================================


class ConfigManager:
    """
    Центральный менеджер конфигурации Exilingo.

    Отвечает за:

    - загрузку config.json;
    - сохранение config.json;
    - значения по умолчанию;
    - доступ к общим настройкам;
    - доступ к настройкам провайдеров;
    - доступ к маршрутам переводчиков;
    - языковые настройки входящих/исходящих переводов.

    Остальная часть приложения не должна самостоятельно
    читать или изменять config.json.
    """

    def __init__(
        self,
        filename: str = CONFIG_FILE,
    ):

        self.filename = Path(filename)

        # Начинаем с полной копии конфигурации
        # по умолчанию.
        self.data = deepcopy(DEFAULT_CONFIG)

        self.load()

    # ======================================================
    # Загрузка
    # ======================================================

    def load(self):
        """
        Загружает config.json.

        Если файл существует, его значения объединяются
        со значениями DEFAULT_CONFIG.

        Это позволяет добавлять новые настройки в будущих
        версиях программы без необходимости вручную
        переписывать старый config.json.
        """

        if not self.filename.exists():
            self.save()

            return

        try:
            with self.filename.open(
                "r",
                encoding="utf-8",
            ) as f:
                loaded = json.load(f)

            if not isinstance(loaded, dict):
                print("[Config] Ошибка: config.json должен содержать JSON-объект.")

                return

            self._merge_dict(
                self.data,
                loaded,
            )

            # Сохраняем после объединения.
            #
            # Это добавляет в старый config.json
            # новые параметры из DEFAULT_CONFIG.
            self.save()

        except Exception as e:
            print(f"[Config] Ошибка загрузки: {e}")

    # ======================================================
    # Сохранение
    # ======================================================

    def save(self):
        """
        Сохраняет текущую конфигурацию в config.json.
        """

        try:
            with self.filename.open(
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    self.data,
                    f,
                    indent=4,
                    ensure_ascii=False,
                )

        except Exception as e:
            print(f"[Config] Ошибка сохранения: {e}")

    # ======================================================
    # Рекурсивное объединение словарей
    # ======================================================

    def _merge_dict(
        self,
        default: dict,
        loaded: dict,
    ):
        """
        Рекурсивно объединяет загруженную конфигурацию
        с конфигурацией по умолчанию.

        Значения из loaded имеют приоритет.

        Отсутствующие новые настройки остаются
        из DEFAULT_CONFIG.
        """

        for key, value in loaded.items():
            if (
                key in default
                and isinstance(default[key], dict)
                and isinstance(value, dict)
            ):
                self._merge_dict(
                    default[key],
                    value,
                )

            else:
                default[key] = value

    # ======================================================
    # Универсальный GET
    # ======================================================

    def get(
        self,
        *keys,
        default=None,
    ):
        """
        Получает значение по цепочке ключей.

        Например:

            config.get(
                "providers",
                "gemini",
                "api_key",
            )
        """

        obj: Any = self.data

        for key in keys:
            if not isinstance(obj, dict):
                return default

            obj = obj.get(key)

            if obj is None:
                return default

        return obj

    # ======================================================
    # Универсальный SET
    # ======================================================

    def set(
        self,
        *keys,
        value,
    ):
        """
        Устанавливает значение по цепочке ключей
        и сразу сохраняет конфигурацию.

        Например:

            config.set(
                "providers",
                "gemini",
                "api_key",
                value="...",
            )
        """

        if not keys:
            raise ValueError("ConfigManager.set() требует хотя бы один ключ.")

        obj = self.data

        for key in keys[:-1]:
            obj = obj.setdefault(
                key,
                {},
            )

        obj[keys[-1]] = value

        self.save()

    # ======================================================
    # Общие настройки
    # ======================================================

    @property
    def log_path(self) -> str:
        """
        Путь к LatestClient.txt.
        """

        return self.get(
            "general",
            "log_path",
            default="",
        )

    @log_path.setter
    def log_path(
        self,
        value: str,
    ):

        self.set(
            "general",
            "log_path",
            value=value,
        )

    # ======================================================
    # Overlay
    # ======================================================

    @property
    def overlay_geometry(self):
        """
        Геометрия Overlay:

        {
            "x": ...,
            "y": ...,
            "w": ...,
            "h": ...
        }
        """

        return self.get(
            "overlay",
            "geometry",
            default=deepcopy(DEFAULT_CONFIG["overlay"]["geometry"]),
        )

    @overlay_geometry.setter
    def overlay_geometry(
        self,
        value,
    ):

        self.set(
            "overlay",
            "geometry",
            value=value,
        )

    # ------------------------------------------------------

    @property
    def font_size(self) -> int:
        """
        Размер шрифта Overlay.
        """

        return self.get(
            "overlay",
            "font_size",
            default=13,
        )

    @font_size.setter
    def font_size(
        self,
        value: int,
    ):

        self.set(
            "overlay",
            "font_size",
            value=value,
        )

    # ======================================================
    # Активный переводчик по умолчанию
    # ======================================================

    @property
    def provider(self) -> str:
        """
        Возвращает первого провайдера из маршрута Global.

        Это временная совместимость со старым кодом.

        В будущем TranslationRouter будет самостоятельно
        выбирать провайдера для каждого типа сообщения.
        """

        route = self.route("global")

        if route:
            return route[0]

        return "google"

    # ======================================================
    # Настройки конкретного провайдера
    # ======================================================

    def get_provider(
        self,
        provider_id: str,
    ) -> dict:
        """
        Возвращает настройки конкретного провайдера.

        Например:

            config.get_provider("gemini")
        """

        return self.get(
            "providers",
            provider_id,
            default={},
        )

    # ------------------------------------------------------

    def set_provider(
        self,
        provider_id: str,
        settings: dict,
    ):
        """
        Полностью заменяет настройки провайдера.
        """

        self.set(
            "providers",
            provider_id,
            value=settings,
        )

    # ------------------------------------------------------

    def provider_enabled(
        self,
        provider_id: str,
    ) -> bool:
        """
        Проверяет, включен ли провайдер.
        """

        return bool(
            self.get(
                "providers",
                provider_id,
                "enabled",
                default=False,
            )
        )

    # ------------------------------------------------------

    def set_provider_enabled(
        self,
        provider_id: str,
        enabled: bool,
    ):
        """
        Включает или выключает провайдера.
        """

        self.set(
            "providers",
            provider_id,
            "enabled",
            value=bool(enabled),
        )

    # ======================================================
    # Языки провайдера
    # ======================================================

    def provider_languages(
        self,
        provider_id: str,
    ) -> tuple[str, str]:
        """
        Возвращает языки провайдера для ВХОДЯЩИХ сообщений.

        Например:

            ("en", "ru")

        Это означает:

            incoming:
                English -> Russian

        Для исходящих сообщений TranslationRouter
        должен автоматически использовать обратное направление:

            outgoing:
                Russian -> English
        """

        provider = self.get_provider(
            provider_id,
        )

        source_language = provider.get(
            "source_language",
            "en",
        )

        target_language = provider.get(
            "target_language",
            "ru",
        )

        return (
            source_language,
            target_language,
        )

    # ------------------------------------------------------

    def provider_source_language(
        self,
        provider_id: str,
    ) -> str:
        """
        Исходный язык для ВХОДЯЩЕГО сообщения.
        """

        source, _ = self.provider_languages(
            provider_id,
        )

        return source

    # ------------------------------------------------------

    def provider_target_language(
        self,
        provider_id: str,
    ) -> str:
        """
        Целевой язык для ВХОДЯЩЕГО сообщения.
        """

        _, target = self.provider_languages(
            provider_id,
        )

        return target

    # ------------------------------------------------------

    def provider_outgoing_languages(
        self,
        provider_id: str,
    ) -> tuple[str, str]:
        """
        Возвращает языковое направление для ИСХОДЯЩЕГО
        сообщения.

        Оно автоматически является обратным направлению
        входящего перевода.

        Например:

            incoming:
                en -> ru

            outgoing:
                ru -> en
        """

        source, target = self.provider_languages(
            provider_id,
        )

        return (
            target,
            source,
        )

    # ------------------------------------------------------

    def provider_outgoing_source_language(
        self,
        provider_id: str,
    ) -> str:
        """
        Исходный язык для исходящего сообщения.
        """

        source, _ = self.provider_outgoing_languages(
            provider_id,
        )

        return source

    # ------------------------------------------------------

    def provider_outgoing_target_language(
        self,
        provider_id: str,
    ) -> str:
        """
        Целевой язык для исходящего сообщения.
        """

        _, target = self.provider_outgoing_languages(
            provider_id,
        )

        return target

    # ======================================================
    # Маршрутизация
    # ======================================================

    def route(
        self,
        channel: str,
    ) -> list[str]:
        """
        Возвращает очередь провайдеров для канала.

        Например:

            config.route("whisper")

        может вернуть:

            [
                "gemini",
                "openrouter",
                "google",
            ]

        Outgoing в будущем должен использовать
        маршрут Whisper.
        """

        # Outgoing не имеет самостоятельной настройки.
        #
        # Он всегда использует очередь Whisper.

        if channel == "outgoing":
            channel = "whisper"

        route = self.get(
            "routing",
            channel,
            default=["google"],
        )

        # Защита от поврежденного config.json.
        if not isinstance(route, list):
            return ["google"]

        return route

    # ------------------------------------------------------

    def set_route(
        self,
        channel: str,
        providers: list[str],
    ):
        """
        Сохраняет очередь провайдеров для канала.

        Outgoing отдельно не сохраняется.
        Его маршрут всегда совпадает с Whisper.
        """

        if channel == "outgoing":
            channel = "whisper"

        self.set(
            "routing",
            channel,
            value=list(providers),
        )

    # ------------------------------------------------------

    def routing(self) -> dict:
        """
        Возвращает всю таблицу маршрутизации.

        При этом Outgoing синхронизируется с Whisper
        для совместимости со старым config.json.
        """

        routing = deepcopy(
            self.get(
                "routing",
                default={},
            )
        )

        if isinstance(routing, dict):
            routing["outgoing"] = list(
                routing.get(
                    "whisper",
                    ["google"],
                )
            )

        return routing

    # ======================================================
    # Сброс настроек провайдера
    # ======================================================

    def reset_provider(
        self,
        provider_id: str,
    ):
        """
        Восстанавливает настройки конкретного провайдера
        из DEFAULT_CONFIG.
        """

        providers = DEFAULT_CONFIG["providers"]

        if provider_id not in providers:
            raise ValueError(f"Неизвестный провайдер: {provider_id}")

        self.set(
            "providers",
            provider_id,
            value=deepcopy(providers[provider_id]),
        )

    # ======================================================
    # Сброс маршрутизации
    # ======================================================

    def reset_routing(self):
        """
        Полностью восстанавливает маршрутизацию
        по умолчанию.
        """

        self.set(
            "routing",
            value=deepcopy(DEFAULT_CONFIG["routing"]),
        )

    # ======================================================
    # Сброс всей конфигурации
    # ======================================================

    def reset_all(self):
        """
        Полностью восстанавливает конфигурацию
        по умолчанию.

        Используется осторожно:
        будут сброшены в том числе путь к
        LatestClient.txt и настройки API-ключей.
        """

        self.data = deepcopy(DEFAULT_CONFIG)

        self.save()


# ==========================================================
# Глобальный объект конфигурации
# ==========================================================

config = ConfigManager()
