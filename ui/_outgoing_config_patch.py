from __future__ import annotations

import json
from pathlib import Path

from core.config_manager import config


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
# Migrate the old Outgoing route into config.json
# ============================================================


def _migrate_outgoing_route() -> None:
    routing = config.data.setdefault("routing", {})

    # New canonical key. It is intentionally not named exactly "outgoing",
    # because old ConfigManager versions interpret that key as a legacy route
    # alias for Whisper and remove it during normalization.
    outgoing = routing.get("outgoing_route")

    if not isinstance(outgoing, list) or not outgoing:
        raw = _read_json(config.filename)
        raw_routing = raw.get("routing", {}) if isinstance(raw, dict) else {}
        if not isinstance(raw_routing, dict):
            raw_routing = {}

        outgoing = raw_routing.get("outgoing_route")

        # First migration: use the user's current Whisper queue. This gives
        # the new Outgoing route the same priority order the user already sees.
        if not isinstance(outgoing, list) or not outgoing:
            outgoing = raw_routing.get("whisper")

        # Very old builds stored only the separate mirror.
        if not isinstance(outgoing, list) or not outgoing:
            legacy = _read_json(config.filename.with_name("outgoing_route.json"))
            if isinstance(legacy, dict):
                outgoing = legacy.get("providers")

    if not isinstance(outgoing, list) or not outgoing:
        outgoing = ["google"]

    outgoing = config._normalize_route(outgoing)
    routing["outgoing_route"] = outgoing

    # This key is ignored by the old normalizer and therefore survives normal
    # application restarts without special migration code in ConfigManager.
    config.save()
    _write_legacy_mirror(outgoing)


_migrate_outgoing_route()


# ============================================================
# ConfigManager route: Outgoing uses its dedicated queue
# ============================================================

_original_config_route = config.route


def _patched_config_route(channel: str):
    if channel == "outgoing":
        route = config.get("routing", "outgoing_route", default=[])
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
            "outgoing_route",
            value=unique,
        )

        _write_legacy_mirror(unique)

    SettingsDialog._save_all_settings = _patched_settings_save

except Exception:
    # SettingsDialog is also wrapped by _settings_dialog_patch.py. The mirror
    # keeps that UI compatible while the TranslationRouter uses config.json.
    pass
