from __future__ import annotations

import json
from pathlib import Path

from core.config_manager import ConfigManager, config


# ============================================================
# Preserve routing.outgoing during ConfigManager normalization
# ============================================================

_original_normalize_config = ConfigManager._normalize_config


def _patched_normalize_config(self):
    routing = self.data.get("routing")
    outgoing = None

    if isinstance(routing, dict):
        value = routing.get("outgoing")
        if isinstance(value, list):
            outgoing = list(value)
        routing.pop("outgoing", None)

    _original_normalize_config(self)

    if outgoing is not None:
        self.data.setdefault("routing", {})["outgoing"] = self._normalize_route(outgoing)


ConfigManager._normalize_config = _patched_normalize_config


# ============================================================
# Helpers for the legacy mirror
# ============================================================


def _read_json(path: Path):
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _write_legacy_mirror(route: list[str]) -> None:
    path = config.filename.with_name("outgoing_route.json")
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump({"providers": route}, handle, ensure_ascii=False, indent=4)
    except Exception:
        pass


# ============================================================
# Migrate the old external outgoing route into config.json
# ============================================================


def _migrate_outgoing_route() -> None:
    raw = _read_json(config.filename)
    raw_routing = raw.get("routing", {}) if isinstance(raw, dict) else {}

    if not isinstance(raw_routing, dict):
        raw_routing = {}

    routing = config.data.setdefault("routing", {})

    # Restore the real existing routes from the raw file before reloading.
    # This repairs configs affected by the previous legacy normalization.
    for channel in ("global", "local", "trade", "party", "guild", "whisper"):
        route = raw_routing.get(channel)
        if isinstance(route, list):
            routing[channel] = list(route)

    outgoing = raw_routing.get("outgoing")

    if not isinstance(outgoing, list) or not outgoing:
        legacy_path = config.filename.with_name("outgoing_route.json")
        legacy = _read_json(legacy_path)
        if isinstance(legacy, dict):
            outgoing = legacy.get("providers")

    if not isinstance(outgoing, list) or not outgoing:
        outgoing = list(routing.get("whisper", ["google"]) or ["google"])

    outgoing = config._normalize_route(outgoing)
    routing["outgoing"] = outgoing

    # Reload once using the patched normalizer. The old normalizer used to
    # migrate outgoing into Whisper and remove it; the patched one preserves it.
    config.load()
    config.data.setdefault("routing", {})["outgoing"] = outgoing

    # Make config.json the canonical persistent source.
    config.save()

    # Keep the old mirror temporarily so the existing settings UI can read it.
    _write_legacy_mirror(outgoing)


_migrate_outgoing_route()


# ============================================================
# ConfigManager route: outgoing comes from config.json
# ============================================================

_original_config_route = config.route


def _patched_config_route(channel: str):
    if channel == "outgoing":
        route = config.get("routing", "outgoing", default=[])
        if isinstance(route, list) and route:
            return config._normalize_route(route)
        return _original_config_route("whisper")

    return _original_config_route(channel)


config.route = _patched_config_route


# ============================================================
# Settings dialog: persist Outgoing into config.json
# ============================================================

try:
    from ui.settings_dialog import SettingsDialog

    _original_settings_save = SettingsDialog._save_all_settings

    def _patched_settings_save(self):
        _original_settings_save(self)

        outgoing = list(
            self.routing_data.get(
                "outgoing",
                config.route("outgoing"),
            )
        )

        outgoing = [
            provider_id
            for provider_id in outgoing
            if self._provider_is_available(provider_id)
        ]

        unique = []
        for provider_id in outgoing:
            if provider_id not in unique:
                unique.append(provider_id)

        if not unique and self.google_enabled.isChecked():
            unique = ["google"]

        config.set(
            "routing",
            "outgoing",
            value=unique,
        )

        _write_legacy_mirror(unique)

    SettingsDialog._save_all_settings = _patched_settings_save

except Exception:
    # SettingsDialog may not be importable yet during package bootstrap.
    # The existing settings patch will still persist the legacy mirror.
    pass
