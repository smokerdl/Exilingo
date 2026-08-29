from __future__ import annotations

import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from .secrets_manager import SecretsManager


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if getattr(sys, "frozen", False):
    CONFIG_BASE_DIR = Path(sys.executable).resolve().parent
else:
    CONFIG_BASE_DIR = PROJECT_ROOT

CONFIG_FILE = CONFIG_BASE_DIR / "config.json"
LEGACY_CONFIG_FILE = PROJECT_ROOT / "config.json"
LEGACY_SECRETS_FILE = PROJECT_ROOT / "secrets.txt"


DEFAULT_CONFIG = {
    "general": {"log_path": ""},
    "overlay": {
        "geometry": {"x": 0, "y": 90, "w": 703, "h": 250},
        "font_size": 14,
    },
    "game_chat": {"input_point": {"x": 0, "y": 0}},
    "providers": {
        "google": {"enabled": True, "source_language": "en", "target_language": "ru"},
        "gemini": {
            "enabled": False,
            "model": "gemini-2.5-flash",
            "system_prompt": "You are a translator of the Path of Exile game chat. Translate naturally without explanations.",
            "source_language": "en",
            "target_language": "ru",
        },
        "groq": {
            "enabled": False,
            "model": "",
            "system_prompt": "",
            "source_language": "en",
            "target_language": "ru",
        },
        "openrouter": {
            "enabled": False,
            "model": "",
            "system_prompt": "",
            "source_language": "en",
            "target_language": "ru",
        },
        "ollama": {
            "enabled": False,
            "host": "http://127.0.0.1:11434",
            "model": "",
            "system_prompt": "",
            "source_language": "en",
            "target_language": "ru",
        },
    },
    "routing": {
        "global": ["google"],
        "local": ["google"],
        "trade": ["google"],
        "party": ["google"],
        "guild": ["google"],
        "whisper": ["google"],
        "outgoing_route": ["google"],
    },
}


class ConfigManager:
    """Central configuration manager for Exilingo."""

    def __init__(self, filename: str | Path = CONFIG_FILE):
        self.filename = Path(filename)
        self.secrets = SecretsManager(self.filename.with_name("secrets.txt"))
        self.data = deepcopy(DEFAULT_CONFIG)
        self._migrate_legacy_secrets()
        self.load()

    def _migrate_legacy_secrets(self) -> None:
        if not getattr(sys, "frozen", False):
            return
        if self.secrets.filename.exists():
            return
        if LEGACY_SECRETS_FILE == self.secrets.filename:
            return
        if not LEGACY_SECRETS_FILE.exists():
            return
        try:
            self.secrets.filename.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(LEGACY_SECRETS_FILE, self.secrets.filename)
        except Exception as exc:
            print(f"[Config] Legacy secrets migration failed: {exc}")

    def _migrate_legacy_file(self) -> bool:
        if not getattr(sys, "frozen", False):
            return False
        if self.filename.exists():
            return False
        if LEGACY_CONFIG_FILE == self.filename or not LEGACY_CONFIG_FILE.exists():
            return False
        try:
            with LEGACY_CONFIG_FILE.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                return False
            self.data = deepcopy(DEFAULT_CONFIG)
            self._merge_dict(self.data, loaded)
            self._migrate_legacy_config(loaded)
            self._normalize_config()
            self.save()
            return True
        except Exception as exc:
            print(f"[Config] Legacy config migration failed: {exc}")
            return False

    def load(self):
        if self._migrate_legacy_file():
            return
        if not self.filename.exists():
            self.save()
            return
        try:
            with self.filename.open("r", encoding="utf-8") as f:
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
            self._merge_dict(self.data, loaded)
            before = deepcopy(self.data)
            self._migrate_legacy_config(loaded)
            self._normalize_config()
            if self.data != before:
                self.save()
        except Exception as exc:
            print(f"[Config] Ошибка загрузки: {exc}")

    def _migrate_legacy_config(self, loaded: dict):
        if not self.get("general", "log_path") and loaded.get("log_path"):
            self.data["general"]["log_path"] = loaded["log_path"]

        legacy_geometry = loaded.get("overlay_geometry")
        current_geometry = self.data.get("overlay", {}).get("geometry", {})
        if isinstance(legacy_geometry, dict):
            default_geometry = DEFAULT_CONFIG["overlay"]["geometry"]
            for key in ("x", "y", "w", "h"):
                if current_geometry.get(key) == default_geometry.get(key) and key in legacy_geometry:
                    current_geometry[key] = legacy_geometry[key]

        if "font_size" in loaded:
            current_font_size = self.data["overlay"].get("font_size", DEFAULT_CONFIG["overlay"]["font_size"])
            if current_font_size == DEFAULT_CONFIG["overlay"]["font_size"]:
                self.data["overlay"]["font_size"] = loaded["font_size"]

        legacy_translation = loaded.get("translation")
        if isinstance(legacy_translation, dict):
            google = self.data["providers"]["google"]
            provider_id = legacy_translation.get("provider")
            if provider_id and provider_id in self.data["providers"]:
                for channel in ("global", "local", "trade", "party", "guild", "whisper"):
                    if self.data["routing"].get(channel, []) == ["google"]:
                        self.data["routing"][channel] = [provider_id]
            if legacy_translation.get("source_language"):
                google["source_language"] = str(legacy_translation["source_language"])
            if legacy_translation.get("target_language"):
                google["target_language"] = str(legacy_translation["target_language"])

        if self.data["routing"].get("outgoing_route") == DEFAULT_CONFIG["routing"]["outgoing_route"]:
            legacy_outgoing = loaded.get("outgoing_route")
            if isinstance(legacy_outgoing, list) and legacy_outgoing:
                self.data["routing"]["outgoing_route"] = legacy_outgoing

    def _normalize_config(self):
        general = self.data.setdefault("general", {})
        if not isinstance(general.get("log_path"), str):
            general["log_path"] = ""

        overlay = self.data.setdefault("overlay", {})
        geometry = overlay.setdefault("geometry", deepcopy(DEFAULT_CONFIG["overlay"]["geometry"]))
        if not isinstance(geometry, dict):
            geometry = deepcopy(DEFAULT_CONFIG["overlay"]["geometry"])
        for key in ("x", "y", "w", "h"):
            try:
                geometry[key] = int(geometry.get(key, DEFAULT_CONFIG["overlay"]["geometry"][key]))
            except (TypeError, ValueError):
                geometry[key] = DEFAULT_CONFIG["overlay"]["geometry"][key]
        overlay["geometry"] = geometry
        try:
            overlay["font_size"] = int(overlay.get("font_size", DEFAULT_CONFIG["overlay"]["font_size"]))
        except (TypeError, ValueError):
            overlay["font_size"] = DEFAULT_CONFIG["overlay"]["font_size"]

        game_chat = self.data.setdefault("game_chat", {})
        input_point = game_chat.setdefault("input_point", deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"]))
        if not isinstance(input_point, dict):
            input_point = deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"])
        for key in ("x", "y"):
            try:
                input_point[key] = int(input_point.get(key, DEFAULT_CONFIG["game_chat"]["input_point"][key]))
            except (TypeError, ValueError):
                input_point[key] = DEFAULT_CONFIG["game_chat"]["input_point"][key]
        game_chat["input_point"] = input_point

        providers = self.data.setdefault("providers", {})
        for provider_id, defaults in DEFAULT_CONFIG["providers"].items():
            provider = providers.setdefault(provider_id, deepcopy(defaults))
            if not isinstance(provider, dict):
                provider = deepcopy(defaults)
                providers[provider_id] = provider
            provider["enabled"] = bool(provider.get("enabled", defaults.get("enabled", False)))
            provider["source_language"] = str(provider.get("source_language", defaults.get("source_language", "en")) or "en").strip() or "en"
            provider["target_language"] = str(provider.get("target_language", defaults.get("target_language", "ru")) or "ru").strip() or "ru"
            if provider_id == "google":
                continue
            if "model" in defaults:
                provider["model"] = str(provider.get("model", defaults.get("model", "")) or "")
            if "system_prompt" in defaults:
                provider["system_prompt"] = str(provider.get("system_prompt", defaults.get("system_prompt", "")) or "")
            if provider_id == "ollama":
                provider["host"] = str(provider.get("host", defaults.get("host", "http://127.0.0.1:11434")) or "").strip()

        routing = self.data.setdefault("routing", {})
        for channel, default_route in DEFAULT_CONFIG["routing"].items():
            route = routing.get(channel, deepcopy(default_route))
            if not isinstance(route, list):
                route = deepcopy(default_route)
            routing[channel] = self._normalize_route(route)

        if "outgoing" in routing:
            legacy = routing.pop("outgoing")
            if routing.get("outgoing_route") == DEFAULT_CONFIG["routing"]["outgoing_route"] and isinstance(legacy, list) and legacy:
                routing["outgoing_route"] = self._normalize_route(legacy)

    def _normalize_route(self, providers: list) -> list[str]:
        if not isinstance(providers, list):
            return ["google"]
        known = set(DEFAULT_CONFIG["providers"].keys())
        result = []
        for provider_id in providers:
            if not isinstance(provider_id, str):
                continue
            provider_id = provider_id.strip()
            if not provider_id or provider_id not in known or provider_id in result:
                continue
            result.append(provider_id)
        return result or ["google"]

    def save(self):
        try:
            self.filename.parent.mkdir(parents=True, exist_ok=True)
            with self.filename.open("w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as exc:
            print(f"[Config] Ошибка сохранения: {exc}")

    def _merge_dict(self, default: dict, loaded: dict):
        for key, value in loaded.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self._merge_dict(default[key], value)
            else:
                default[key] = value

    def get(self, *keys, default=None):
        obj: Any = self.data
        for key in keys:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(key)
            if obj is None:
                return default
        return obj

    def set(self, *keys, value):
        if not keys:
            raise ValueError("ConfigManager.set() требует хотя бы один ключ.")
        obj = self.data
        for key in keys[:-1]:
            obj = obj.setdefault(key, {})
        obj[keys[-1]] = value
        self.save()

    @property
    def log_path(self) -> str:
        return self.get("general", "log_path", default="")

    @log_path.setter
    def log_path(self, value: str):
        self.set("general", "log_path", value=value)

    @property
    def overlay_geometry(self):
        return self.get("overlay", "geometry", default=deepcopy(DEFAULT_CONFIG["overlay"]["geometry"]))

    @overlay_geometry.setter
    def overlay_geometry(self, value):
        self.set("overlay", "geometry", value=value)

    @property
    def font_size(self) -> int:
        return self.get("overlay", "font_size", default=14)

    @font_size.setter
    def font_size(self, value: int):
        self.set("overlay", "font_size", value=value)

    @property
    def game_chat_input_point(self) -> dict:
        point = self.get("game_chat", "input_point", default=deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"]))
        if not isinstance(point, dict):
            return deepcopy(DEFAULT_CONFIG["game_chat"]["input_point"])
        return {"x": int(point.get("x", 0)), "y": int(point.get("y", 0))}

    @game_chat_input_point.setter
    def game_chat_input_point(self, value: dict):
        if not isinstance(value, dict):
            raise ValueError("game_chat_input_point должен быть dict.")
        try:
            x = int(value.get("x", 0))
            y = int(value.get("y", 0))
        except (TypeError, ValueError):
            raise ValueError("Координаты точки должны быть целыми числами.")
        self.set("game_chat", "input_point", value={"x": x, "y": y})

    def set_game_chat_input_point(self, x: int, y: int):
        self.game_chat_input_point = {"x": x, "y": y}

    @property
    def game_chat_input_point_configured(self) -> bool:
        point = self.game_chat_input_point
        return point["x"] != 0 or point["y"] != 0

    @property
    def provider(self) -> str:
        route = self.route("global")
        return route[0] if route else "google"

    def get_provider(self, provider_id: str) -> dict:
        result = self.get("providers", provider_id, default={})
        return result if isinstance(result, dict) else {}

    def set_provider(self, provider_id: str, settings: dict):
        self.set("providers", provider_id, value=dict(settings))

    def provider_enabled(self, provider_id: str) -> bool:
        return bool(self.get("providers", provider_id, "enabled", default=False))

    def set_provider_enabled(self, provider_id: str, enabled: bool):
        self.set("providers", provider_id, "enabled", value=bool(enabled))

    def provider_api_key(self, provider_id: str) -> str:
        if provider_id not in ("gemini", "groq", "openrouter"):
            return ""
        return self.secrets.get(f"{provider_id}_api_key")

    def set_provider_api_key(self, provider_id: str, api_key: str) -> None:
        if provider_id not in ("gemini", "groq", "openrouter"):
            raise ValueError(f"Провайдер '{provider_id}' не использует API key.")
        self.secrets.set(f"{provider_id}_api_key", api_key)

    def provider_languages(self, provider_id: str) -> tuple[str, str]:
        provider = self.get_provider(provider_id)
        return (
            str(provider.get("source_language", "en") or "en").strip() or "en",
            str(provider.get("target_language", "ru") or "ru").strip() or "ru",
        )

    def provider_source_language(self, provider_id: str) -> str:
        return self.provider_languages(provider_id)[0]

    def provider_target_language(self, provider_id: str) -> str:
        return self.provider_languages(provider_id)[1]

    def provider_outgoing_languages(self, provider_id: str) -> tuple[str, str]:
        source, target = self.provider_languages(provider_id)
        return target, source

    def route(self, channel: str) -> list[str]:
        if channel == "outgoing":
            channel = "outgoing_route"
        return self._normalize_route(self.get("routing", channel, default=["google"]))

    def set_route(self, channel: str, providers: list[str]):
        if channel == "outgoing":
            channel = "outgoing_route"
        self.set("routing", channel, value=self._normalize_route(providers))

    def routing(self) -> dict:
        return {channel: self.route(channel) for channel in DEFAULT_CONFIG["routing"]}

    def reset_provider(self, provider_id: str):
        providers = DEFAULT_CONFIG["providers"]
        if provider_id not in providers:
            raise ValueError(f"Неизвестный провайдер: {provider_id}")
        self.set("providers", provider_id, value=deepcopy(providers[provider_id]))
        if provider_id in ("gemini", "groq", "openrouter"):
            self.set_provider_api_key(provider_id, "")

    def reset_routing(self):
        self.set("routing", value=deepcopy(DEFAULT_CONFIG["routing"]))

    def reset_all(self):
        self.data = deepcopy(DEFAULT_CONFIG)
        for provider_id in ("gemini", "groq", "openrouter"):
            self.set_provider_api_key(provider_id, "")
        self.save()


config = ConfigManager()
