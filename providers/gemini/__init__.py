from .translator import GeminiTranslator

__all__ = ["GeminiTranslator"]


# ============================================================
# Gemini default-settings migration
# ============================================================
#
# ConfigManager is loaded before ProviderRegistry, which imports
# this package. This gives us a safe one-time migration point before
# the startup settings snapshot is written to exilingo.log.


def _migrate_defaults():
    try:
        from core.config_manager import config

        migration_key = "gemini_defaults_v1"
        migrations = config.get("migrations", default={})

        if isinstance(migrations, dict) and migrations.get(migration_key):
            return

        gemini = config.get("providers", "gemini", default={})

        if isinstance(gemini, dict):
            model = str(gemini.get("model", "") or "").strip()

            if not model or model == "gemini-2.5-flash":
                gemini["model"] = "gemini-3.5-flash-lite"

            # Gemini remains disabled until the user configures it.
            gemini["enabled"] = bool(gemini.get("enabled", False))

        routing = config.get("routing", default={})

        if isinstance(routing, dict):
            # Migrate only the old untouched Google-only defaults.
            for channel in ("whisper", "party"):
                if routing.get(channel) == ["google"]:
                    routing[channel] = ["gemini", "google"]

        if not isinstance(migrations, dict):
            migrations = {}
            config.data["migrations"] = migrations

        migrations[migration_key] = True
        config.save()

    except Exception:
        # A migration must never prevent Exilingo from starting.
        pass


_migrate_defaults()
