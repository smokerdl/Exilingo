from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .secrets_manager import SecretsManager


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
    # Игровой чат
    # ------------------------------------------------------
    #
    # Координаты точки активации строки ввода сообщений
    # игрового чата в экранных координатах Windows.
    #
    # x=0, y=0 означает, что точка ещё не откалибрована.
    #
    "game_chat": {
        "input_point": {
            "x": 0,
            "y": 0,
        },
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
            # incoming:
            #     en -> ru
            #
            # outgoing автоматически:
            #     ru -> en
            #
            "source_language": "en",
            "target_language": "ru",
        },
        # --------------------------------------------------
        # Gemini
        # --------------------------------------------------
        "gemini": {
            "enabled": False,
            "model": "gemini-2.5-flash",
            "system_prompt": (
                "You are a translator of the Path of Exile game chat. "
                "Translate naturally without explanations."
            ),
            "source_language": "en",
            "target_language": "ru",
        },
        # --------------------------------------------------
        # Groq
        # --------------------------------------------------
        "groq": {
            "enabled": False,
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
    # Каждый канал содержит ОЧЕРЕДЬ провайдеров.
    #
    # Например:
    #
    # "whisper": [
    #     "gemini",
    #     "openrouter",
    #     "google",
    # ]
    #
    # TranslationRouter пробует провайдеров
    # именно в указанном порядке.
    #
    # Outgoing здесь намеренно НЕТ.
    #
    # Исходящие сообщения используют тот же маршрут,
    # что и Whisper.
    #
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
    - миграцию старой конфигурации;
    - доступ к общим настройкам;
    - доступ к настройкам Overlay;
    - доступ к точке активации игрового чата;
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
        self.secrets = SecretsManager(self.filename.with_name("secrets.txt"))

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

        После загрузки выполняется миграция старых
        параметров конфигурации.
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

            providers = loaded.get("providers", {})
            if isinstance(providers, dict):
                self.secrets.migrate_from_config(providers)
                for provider in providers.values():
                    if isinstance(provider, dict):
                        provider.pop("api_key", None)

            self._merge_dict(
                self.data,
                loaded,
            )

            self._migrate_legacy_config(
                loaded,
            )

            self._normalize_config()

            self.save()

        except Exception as e:
            print(f"[Config] Ошибка загрузки: {e}")

    # ======================================================
    # Миграция старой конфигурации
    # ======================================================

    def _migrate_legacy_config(
        self,
        loaded: dict,
    ):
        """
        Переносит настройки из старых версий Exilingo.
        """

        # --------------------------------------------------
        # Старый log_path
        # --------------------------------------------------

        if not self.get("general", "log_path") and loaded.get("log_path"):
            self.data["general"]["log_path"] = loaded["log_path"]

        # --------------------------------------------------
        # Старый overlay_geometry
        # --------------------------------------------------

        legacy_geometry = loaded.get(
            "overlay_geometry",
        )

        current_geometry = self.data.get(
            "overlay",
            {},
        ).get(
            "geometry",
            {},
        )

        if isinstance(legacy_geometry, dict):
            default_geometry = DEFAULT_CONFIG["overlay"]["geometry"]

            for key in (
                "x",
                "y",
                "w",
                "h",
            ):
                if (
                    current_geometry.get(key) == default_geometry.get(key)
                    and key in legacy_geometry
                ):
                    current_geometry[key] = legacy_geometry[key]

        # --------------------------------------------------
        # Старый font_size
        # --------------------------------------------------

        if "font_size" in loaded:
            current_font_size = self.data["overlay"].get(
                "font_size",
                DEFAULT_CONFIG["overlay"]["font_size"],
            )

            if current_font_size == DEFAULT_CONFIG["overlay"]["font_size"]:
                self.data["overlay"]["font_size"] = loaded["font_size"]

        # --------------------------------------------------
        # Старый translation
        # --------------------------------------------------

        legacy_translation = loaded.get(
            "translation",
        )

        if isinstance(legacy_translation, dict):
            google = self.data["providers"]["google"]

            if "provider" in legacy_translation and legacy_translation["provider"]:
                provider_id = str(legacy_translation["provider"])

                if provider_id in self.data["providers"]:
                    for channel in (
                        "global",
                        "local",
                        "trade",
                        "party",
                        "guild",
                        "whisper",
                    ):
                        route = self.data["routing"].get(
                            channel,
                            [],
                        )

                        if route == ["google"]:
                            self.data["routing"][channel] = [provider_id]

            if (
                "source_language" in legacy_translation
                and legacy_translation["source_language"]
            ):
                google["source_language"] = str(legacy_translation["source_language"])

            if (
                "target_language" in legacy_translation
                and legacy_translation["target_language"]
            ):
                google["target_language"] = str(legacy_translation["target_language"])

    # ======================================================
    # Нормализация конфигурации
    # ======================================================

    def _normalize_config(self):
        """
        Проверяет и нормализует структуру конфигурации.
        """

        # --------------------------------------------------
        # General
        # --------------------------------------------------

        general = self.data.setdefault(
            "general",
            {},
        )

        if not isinstance(
            general.get("log_path"),
            str,
        ):
            general["log_path"] = ""

        # --------------------------------------------------
        # Overlay
        # --------------------------------------------------

        overlay = self.data.setdefault(
            "overlay",
            {},
        )

        geometry = overlay.setdefault(
            "geometry",
            deepcopy(DEFAULT_CONFIG["overlay"]["geometry"]),
        )

        if not isinstance(
            geometry,
            dict,
        ):
            geometry = deepcopy(DEFAULT_CONFIG["overlay"]["geometry"])

        for key in (
            "x",
            "y",
            "w",
            "h",
        ):
            default_value = DEFAULT_CONFIG["overlay"]["geometry"][key]

            value = geometry.get(
                key,
                default_value,
            )

            try:
                geometry[key] = int(value)

            except (TypeError, ValueError):
                geometry[key] = default_value

        overlay["geometry"] = geometry

        try:
            overlay["font_size"] = int(
                overlay.get(
                    "font_size",
                    DEFAULT_CONFIG["overlay"]["font_size"],
                )
            )

        except (TypeError, ValueError):
            overlay["font_size"] = DEFAULT_CONFIG["overlay"]["font_size"]

        # --------------------------------------------------
        # Game chat
        # --------------------------------------------------

        game_chat = self.data.setdefault(
            "game_chat",
            {},
        )

        input_point = game_chat.setdefault(
            "input_point",
            deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"]),
        )

        if not isinstance(
            input_point,
            dict,
        ):
            input_point = deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"])

        for key in (
            "x",
            "y",
        ):
            default_value = DEFAULT_CONFIG["game_chat"]["input_point"][key]

            value = input_point.get(
                key,
                default_value,
            )

            try:
                input_point[key] = int(value)

            except (TypeError, ValueError):
                input_point[key] = default_value

        game_chat["input_point"] = input_point

        # --------------------------------------------------
        # Providers
        # --------------------------------------------------

        providers = self.data.setdefault(
            "providers",
            {},
        )

        for provider_id, defaults in DEFAULT_CONFIG["providers"].items():
            provider = providers.setdefault(
                provider_id,
                deepcopy(defaults),
            )

            if not isinstance(
                provider,
                dict,
            ):
                provider = deepcopy(defaults)
                providers[provider_id] = provider

            provider["enabled"] = bool(
                provider.get(
                    "enabled",
                    defaults.get(
                        "enabled",
                        False,
                    ),
                )
            )

            source_language = provider.get(
                "source_language",
                defaults.get(
                    "source_language",
                    "en",
                ),
            )

            target_language = provider.get(
                "target_language",
                defaults.get(
                    "target_language",
                    "ru",
                ),
            )

            provider["source_language"] = str(source_language or "en").strip() or "en"

            provider["target_language"] = str(target_language or "ru").strip() or "ru"

            if provider_id == "google":
                continue

            if "model" in defaults:
                provider["model"] = str(
                    provider.get(
                        "model",
                        defaults.get(
                            "model",
                            "",
                        ),
                    )
                    or ""
                )

            if "system_prompt" in defaults:
                provider["system_prompt"] = str(
                    provider.get(
                        "system_prompt",
                        defaults.get(
                            "system_prompt",
                            "",
                        ),
                    )
                    or ""
                )

            if provider_id == "ollama":
                provider["host"] = str(
                    provider.get(
                        "host",
                        defaults.get(
                            "host",
                            "http://127.0.0.1:11434",
                        ),
                    )
                    or ""
                ).strip()

        # --------------------------------------------------
        # Routing
        # --------------------------------------------------

        routing = self.data.setdefault(
            "routing",
            {},
        )

        for (
            channel,
            default_route,
        ) in DEFAULT_CONFIG["routing"].items():
            route = routing.get(
                channel,
                deepcopy(default_route),
            )

            if not isinstance(
                route,
                list,
            ):
                route = deepcopy(default_route)

            routing[channel] = self._normalize_route(
                route,
            )

        # --------------------------------------------------
        # Legacy outgoing route
        # --------------------------------------------------

        legacy_outgoing = routing.get(
            "outgoing",
        )

        if isinstance(
            legacy_outgoing,
            list,
        ):
            whisper_route = routing.get(
                "whisper",
                [],
            )

            if (
                whisper_route == DEFAULT_CONFIG["routing"]["whisper"]
                and legacy_outgoing
            ):
                routing["whisper"] = self._normalize_route(
                    legacy_outgoing,
                )

            routing.pop(
                "outgoing",
                None,
            )

    # ======================================================
    # Нормализация маршрута
    # ======================================================

    def _normalize_route(
        self,
        providers: list,
    ) -> list[str]:

        if not isinstance(
            providers,
            list,
        ):
            return ["google"]

        known_providers = set(DEFAULT_CONFIG["providers"].keys())

        result = []

        for provider_id in providers:
            if not isinstance(
                provider_id,
                str,
            ):
                continue

            provider_id = provider_id.strip()

            if not provider_id:
                continue

            if provider_id not in known_providers:
                continue

            if provider_id in result:
                continue

            result.append(provider_id)

        if not result:
            return ["google"]

        return result

    # ======================================================
    # Сохранение
    # ======================================================

    def save(self):
        """
        Сохраняет текущую конфигурацию.
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
        Рекурсивно объединяет конфигурацию.
        """

        for key, value in loaded.items():
            if (
                key in default
                and isinstance(
                    default[key],
                    dict,
                )
                and isinstance(
                    value,
                    dict,
                )
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
        """

        obj: Any = self.data

        for key in keys:
            if not isinstance(
                obj,
                dict,
            ):
                return default

            obj = obj.get(
                key,
            )

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
    # Точка активации строки ввода игрового чата
    # ======================================================

    @property
    def game_chat_input_point(self) -> dict:
        """
        Возвращает экранную координату точки,
        по которой необходимо кликнуть для активации
        строки ввода сообщений игрового чата.

        Формат:

            {
                "x": 742,
                "y": 1012
            }

        Координаты задаются относительно всего экрана.

        {0, 0} означает, что точка ещё не откалибрована.
        """

        point = self.get(
            "game_chat",
            "input_point",
            default=deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"]),
        )

        if not isinstance(
            point,
            dict,
        ):
            return deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"])

        return {
            "x": int(
                point.get(
                    "x",
                    0,
                )
            ),
            "y": int(
                point.get(
                    "y",
                    0,
                )
            ),
        }

    @game_chat_input_point.setter
    def game_chat_input_point(
        self,
        value: dict,
    ):
        """
        Устанавливает экранную координату точки
        активации строки ввода игрового чата.
        """

        if not isinstance(
            value,
            dict,
        ):
            raise ValueError("game_chat_input_point должен быть dict.")

        try:
            x = int(
                value.get(
                    "x",
                    0,
                )
            )

            y = int(
                value.get(
                    "y",
                    0,
                )
            )

        except (TypeError, ValueError):
            raise ValueError("Координаты точки должны быть целыми числами.")

        self.set(
            "game_chat",
            "input_point",
            value={
                "x": x,
                "y": y,
            },
        )

    # ------------------------------------------------------

    def set_game_chat_input_point(
        self,
        x: int,
        y: int,
    ):
        """
        Устанавливает точку активации строки ввода
        игрового чата.

        Координаты являются экранными координатами Windows.
        """

        self.game_chat_input_point = {
            "x": x,
            "y": y,
        }

    # ------------------------------------------------------

    @property
    def game_chat_input_point_configured(self) -> bool:
        """
        Возвращает True, если точка активации
        строки ввода игрового чата уже откалибрована.
        """

        point = self.game_chat_input_point

        return point["x"] != 0 or point["y"] != 0

    # ======================================================
    # Активный переводчик по умолчанию
    # ======================================================

    @property
    def provider(self) -> str:
        """
        Возвращает первого провайдера из маршрута Global.

        Это временная совместимость со старым кодом.
        """

        route = self.route(
            "global",
        )

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

        result = self.get(
            "providers",
            provider_id,
            default={},
        )

        if not isinstance(
            result,
            dict,
        ):
            return {}

        return result

    # ------------------------------------------------------

    def set_provider(
        self,
        provider_id: str,
        settings: dict,
    ):

        self.set(
            "providers",
            provider_id,
            value=dict(settings),
        )

    # ------------------------------------------------------

    def provider_enabled(
        self,
        provider_id: str,
    ) -> bool:

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

        self.set(
            "providers",
            provider_id,
            "enabled",
            value=bool(enabled),
        )

    # ======================================================
    # API-ключи (хранятся отдельно от config.json)
    # ======================================================

    def provider_api_key(self, provider_id: str) -> str:
        if provider_id not in ("gemini", "groq", "openrouter"):
            return ""
        return self.secrets.get(f"{provider_id}_api_key")

    def set_provider_api_key(self, provider_id: str, api_key: str) -> None:
        if provider_id not in ("gemini", "groq", "openrouter"):
            raise ValueError(f"Провайдер '{provider_id}' не использует API key.")
        self.secrets.set(f"{provider_id}_api_key", api_key)

    # ======================================================
    # Языки провайдера
    # ======================================================

    def provider_languages(
        self,
        provider_id: str,
    ) -> tuple[str, str]:

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

        source_language = str(source_language or "en").strip() or "en"

        target_language = str(target_language or "ru").strip() or "ru"

        return (
            source_language,
            target_language,
        )

    # ------------------------------------------------------

    def provider_source_language(
        self,
        provider_id: str,
    ) -> str:

        source, _ = self.provider_languages(
            provider_id,
        )

        return source

    # ------------------------------------------------------

    def provider_target_language(
        self,
        provider_id: str,
    ) -> str:

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
        Возвращает языковое направление для исходящего
        сообщения.

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

    # ======================================================
    # Маршрутизация
    # ======================================================

    def route(
        self,
        channel: str,
    ) -> list[str]:
        """
        Возвращает очередь провайдеров для канала.

        Outgoing автоматически использует Whisper.
        """

        if channel == "outgoing":
            channel = "whisper"

        route = self.get(
            "routing",
            channel,
            default=["google"],
        )

        return self._normalize_route(
            route,
        )

    # ------------------------------------------------------

    def set_route(
        self,
        channel: str,
        providers: list[str],
    ):
        """
        Сохраняет очередь провайдеров для канала.

        Outgoing записывается в Whisper.
        """

        if channel == "outgoing":
            channel = "whisper"

        self.set(
            "routing",
            channel,
            value=self._normalize_route(
                providers,
            ),
        )

    # ------------------------------------------------------

    def routing(self) -> dict:
        """
        Возвращает таблицу маршрутизации.

        Outgoing намеренно отсутствует.
        """

        result = {}

        for channel in DEFAULT_CONFIG["routing"]:
            result[channel] = self.route(
                channel,
            )

        return result

    # ======================================================
    # Сброс настроек провайдера
    # ======================================================

    def reset_provider(
        self,
        provider_id: str,
    ):

        providers = DEFAULT_CONFIG["providers"]

        if provider_id not in providers:
            raise ValueError(f"Неизвестный провайдер: {provider_id}")

        self.set(
            "providers",
            provider_id,
            value=deepcopy(providers[provider_id]),
        )
        if provider_id in ("gemini", "groq", "openrouter"):
            self.set_provider_api_key(provider_id, "")

    # ======================================================
    # Сброс маршрутизации
    # ======================================================

    def reset_routing(self):

        self.set(
            "routing",
            value=deepcopy(DEFAULT_CONFIG["routing"]),
        )

    # ======================================================
    # Сброс всей конфигурации
    # ======================================================

    def reset_all(self):

        self.data = deepcopy(DEFAULT_CONFIG)
        for provider_id in ("gemini", "groq", "openrouter"):
            self.set_provider_api_key(provider_id, "")

        self.save()


# ==========================================================
# Глобальный объект конфигурации
# ==========================================================

config = ConfigManager()
