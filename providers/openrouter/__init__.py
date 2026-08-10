from .translator import OpenRouterTranslator

__all__ = ["OpenRouterTranslator"]


# ============================================================
# OpenRouter default-settings migration
# ============================================================


def _migrate_defaults():
    try:
        from core.config_manager import config

        migration_key = "openrouter_defaults_v1"
        migrations = config.get("migrations", default={})

        if isinstance(migrations, dict) and migrations.get(migration_key):
            return

        openrouter = config.get("providers", "openrouter", default={})

        if isinstance(openrouter, dict):
            model = str(openrouter.get("model", "") or "").strip()
            if not model:
                openrouter["model"] = "gpt-oss-20b:free"

            if not str(openrouter.get("system_prompt", "") or "").strip():
                openrouter["system_prompt"] = (
                    "You are a translator of the Path of Exile game chat. "
                    "Translate naturally without explanations."
                )

            openrouter["enabled"] = bool(openrouter.get("enabled", False))

        if not isinstance(migrations, dict):
            migrations = {}
            config.data["migrations"] = migrations

        migrations[migration_key] = True
        config.save()

    except Exception:
        # A migration must never prevent Exilingo from starting.
        pass


_migrate_defaults()
