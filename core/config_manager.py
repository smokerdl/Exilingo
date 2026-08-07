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
            "api_key": "",
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
    # Это позволяет не дублировать одну и ту же
    # очередь в настройках.
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

            # Сначала объединяем старую конфигурацию
            # с актуальными значениями по умолчанию.
            self._merge_dict(
                self.data,
                loaded,
            )

            # Затем переносим старые параметры
            # в актуальную структуру.
            self._migrate_legacy_config(
                loaded,
            )

            # Нормализуем структуру.
            self._normalize_config()

            # Сохраняем уже актуальную конфигурацию.
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

        Ранее часть настроек могла находиться непосредственно
        в корне config.json:

            "log_path"
            "overlay_geometry"
            "font_size"
            "translation"

        Теперь они находятся в:

            general.log_path
            overlay.geometry
            overlay.font_size
            providers / routing

        При наличии новой структуры она имеет приоритет.
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

            # Переносим только отсутствующие значения.
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
        #
        # Старые версии могли хранить:
        #
        # "translation": {
        #     "provider": "google",
        #     "source_language": "en",
        #     "target_language": "ru"
        # }
        #
        # Переносим эти данные в Google, если актуальные
        # значения ещё не были настроены.
        # --------------------------------------------------

        legacy_translation = loaded.get(
            "translation",
        )

        if isinstance(legacy_translation, dict):
            google = self.data["providers"]["google"]

            if "provider" in legacy_translation and legacy_translation["provider"]:
                provider_id = str(legacy_translation["provider"])

                if provider_id in self.data["providers"]:
                    # Старый provider использовался как
                    # единственный активный переводчик.
                    #
                    # Добавляем его в Global/Whisper только
                    # если текущий маршрут ещё стандартный.
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

        Здесь мы не меняем пользовательские значения
        без необходимости, а только защищаем приложение
        от поврежденных или устаревших данных.
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

        if not isinstance(geometry, dict):
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

            if not isinstance(provider, dict):
                provider = deepcopy(defaults)
                providers[provider_id] = provider

            provider["enabled"] = bool(
                provider.get(
                    "enabled",
                    defaults.get("enabled", False),
                )
            )

            # Все провайдеры используют единое
            # представление направления.
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
                        defaults.get("model", ""),
                    )
                    or ""
                )

            if "system_prompt" in defaults:
                provider["system_prompt"] = str(
                    provider.get(
                        "system_prompt",
                        defaults.get("system_prompt", ""),
                    )
                    or ""
                )

            if "api_key" in defaults:
                provider["api_key"] = str(
                    provider.get(
                        "api_key",
                        "",
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

        for channel, default_route in DEFAULT_CONFIG["routing"].items():
            route = routing.get(
                channel,
                deepcopy(default_route),
            )

            if not isinstance(route, list):
                route = deepcopy(default_route)

            routing[channel] = self._normalize_route(
                route,
            )

        # --------------------------------------------------
        # Legacy outgoing route
        # --------------------------------------------------
        #
        # Outgoing больше не является самостоятельной
        # настройкой.
        #
        # Если старый config.json содержит outgoing,
        # его маршрут переносим в whisper, если whisper
        # ещё не был явно изменён.
        # --------------------------------------------------

        legacy_outgoing = routing.get(
            "outgoing",
        )

        if isinstance(legacy_outgoing, list):
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
        """
        Удаляет поврежденные значения и дубликаты
        из очереди провайдеров.
        """

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

        Например:

            config.get(
                "providers",
                "gemini",
                "api_key",
            )
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
        """
        Возвращает настройки конкретного провайдера.
        """

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
        """
        Полностью заменяет настройки провайдера.
        """

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

        означает:

            incoming:
                English -> Russian

        Для исходящих используется обратное направление.
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

        Направление автоматически является обратным
        направлению входящего перевода.

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

    # ======================================================
    # Маршрутизация
    # ======================================================

    def route(
        self,
        channel: str,
    ) -> list[str]:
        """
        Возвращает очередь провайдеров для канала.

        Особый случай:

            route("outgoing")

        автоматически возвращает маршрут Whisper.

        Outgoing не хранится отдельно в config.json,
        поскольку используется тот же маршрут.
        """

        # --------------------------------------------------
        # Outgoing = Whisper
        # --------------------------------------------------

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

        Outgoing не имеет собственной очереди.
        При попытке сохранить outgoing данные записываются
        в whisper.
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
        Возвращает всю таблицу маршрутизации.

        Outgoing здесь намеренно отсутствует.
        """

        routing = self.get(
            "routing",
            default={},
        )

        if not isinstance(
            routing,
            dict,
        ):
            return {}

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
        будут сброшены путь к LatestClient.txt,
        API-ключи и настройки провайдеров.
        """

        self.data = deepcopy(DEFAULT_CONFIG)

        self.save()


# ==========================================================
# Глобальный объект конфигурации
# ==========================================================

config = ConfigManager()
