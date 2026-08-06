from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


CONFIG_FILE = "config.json"


DEFAULT_CONFIG = {
    # --------------------------------------------------
    # Общие настройки
    # --------------------------------------------------
    "general": {
        "log_path": "",
    },
    # --------------------------------------------------
    # Overlay
    # --------------------------------------------------
    "overlay": {
        "geometry": {
            "x": 1,
            "y": 11,
            "w": 700,
            "h": 309,
        },
        "font_size": 13,
    },
    # --------------------------------------------------
    # Переводчики
    # --------------------------------------------------
    "providers": {
        "google": {
            "enabled": True,
            "source_language": "en",
            "target_language": "ru",
        },
        "gemini": {
            "enabled": False,
            "api_key": "",
            "model": "gemini-2.5-flash",
            "system_prompt": "You are a translator of the Path of Exile game chat. "
            "Translate naturally without explanations.",
        },
        "groq": {
            "enabled": False,
            "api_key": "",
            "model": "",
            "system_prompt": "",
        },
        "openrouter": {
            "enabled": False,
            "api_key": "",
            "model": "",
            "system_prompt": "",
        },
        "ollama": {
            "enabled": False,
            "host": "http://127.0.0.1:11434",
            "model": "",
            "system_prompt": "",
        },
    },
    # --------------------------------------------------
    # Маршрутизация
    # --------------------------------------------------
    "routing": {
        "global": ["google"],
        "trade": ["google"],
        "party": ["google"],
        "guild": ["google"],
        "whisper": ["google"],
        "outgoing": ["google"],
    },
}


class ConfigManager:
    def __init__(self, filename: str = CONFIG_FILE):

        self.filename = Path(filename)

        self.data = deepcopy(DEFAULT_CONFIG)

        self.load()

    # =====================================================
    # Загрузка
    # =====================================================

    def load(self):

        if not self.filename.exists():
            self.save()
            return

        try:
            with self.filename.open(
                "r",
                encoding="utf-8",
            ) as f:
                loaded = json.load(f)

            self._merge_dict(
                self.data,
                loaded,
            )

        except Exception as e:
            print(f"[Config] Ошибка загрузки: {e}")

    # =====================================================
    # Сохранение
    # =====================================================

    def save(self):

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

    # =====================================================
    # Объединение словарей
    # =====================================================

    def _merge_dict(
        self,
        default: dict,
        loaded: dict,
    ):

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

    # =====================================================
    # Универсальный GET
    # =====================================================

    def get(
        self,
        *keys,
        default=None,
    ):

        obj: Any = self.data

        for key in keys:
            if not isinstance(obj, dict):
                return default

            obj = obj.get(key)

            if obj is None:
                return default

        return obj

    # =====================================================
    # Универсальный SET
    # =====================================================

    def set(
        self,
        *keys,
        value,
    ):

        obj = self.data

        for key in keys[:-1]:
            obj = obj.setdefault(key, {})

        obj[keys[-1]] = value

        self.save()

    # =====================================================
    # Общие настройки
    # =====================================================

    @property
    def log_path(self):

        return self.get(
            "general",
            "log_path",
            default="",
        )

    @log_path.setter
    def log_path(
        self,
        value,
    ):

        self.set(
            "general",
            "log_path",
            value=value,
        )

    # =====================================================
    # Overlay
    # =====================================================

    @property
    def overlay_geometry(self):

        return self.get(
            "overlay",
            "geometry",
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

    @property
    def font_size(self):

        return self.get(
            "overlay",
            "font_size",
            default=13,
        )

    @font_size.setter
    def font_size(
        self,
        value,
    ):

        self.set(
            "overlay",
            "font_size",
            value=value,
        )

    # =====================================================
    # Активный переводчик по умолчанию
    # =====================================================

    @property
    def provider(self) -> str:
        """
        Возвращает первый переводчик
        из маршрута Global.
        """

        route = self.route("global")

        if route:
            return route[0]

        return "google"

    # =====================================================
    # Настройки конкретного провайдера
    # =====================================================

    def get_provider(
        self,
        provider_id: str,
    ):

        return self.get(
            "providers",
            provider_id,
            default={},
        )

    # =====================================================
    # Маршрутизация
    # =====================================================

    def route(
        self,
        channel: str,
    ):

        return self.get(
            "routing",
            channel,
            default=["google"],
        )

    # =====================================================
    # Текущий провайдер по умолчанию
    # =====================================================

    @property
    def provider(self) -> str:
        """
        Возвращает первый провайдер,
        назначенный для глобального чата.

        Пока используется как провайдер
        по умолчанию для всего приложения.

        Позже TranslationRouter будет выбирать
        провайдера самостоятельно для каждого
        типа сообщений.
        """

        route = self.route("global")

        if route:
            return route[0]

        return "google"


config = ConfigManager()
