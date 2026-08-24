from __future__ import annotations

from core.config_manager import config
from . import _settings_dialog_patch as settings_patch


# The legacy UI patch still exposes helper functions for Outgoing routing.
# Redirect them to the canonical routing.outgoing_route entry in config.json.
def _load_outgoing_route() -> list[str]:
    route = config.get("routing", "outgoing_route", default=[])
    if isinstance(route, list) and route:
        return config._normalize_route(route)
    return config.route("whisper")


def _save_outgoing_route(route: list[str]) -> None:
    config.set(
        "routing",
        "outgoing_route",
        value=config._normalize_route(route),
    )


settings_patch._load_outgoing_route = _load_outgoing_route
settings_patch._save_outgoing_route = _save_outgoing_route


# TranslationRouter already maps outgoing -> "outgoing". The config manager
# resolves that public channel name to routing.outgoing_route.
_original_config_route = config.route


def _patched_config_route(channel: str) -> list[str]:
    if channel == "outgoing":
        return _load_outgoing_route()
    return _original_config_route(channel)


config.route = _patched_config_route
