from __future__ import annotations

from pathlib import Path


class SecretsManager:
    """Local plaintext secret storage. secrets.txt must never be committed."""

    def __init__(self, filename: str = "secrets.txt"):
        self.filename = Path(filename)

    def _read(self) -> dict[str, str]:
        if not self.filename.exists():
            return {}
        result: dict[str, str] = {}
        for raw_line in self.filename.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
        return result

    def _write(self, values: dict[str, str]) -> None:
        lines = ["# Exilingo local secrets. DO NOT COMMIT THIS FILE."]
        lines.extend(f"{key}={value}" for key, value in values.items())
        self.filename.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get(self, key: str, default: str = "") -> str:
        return self._read().get(key, default)

    def set(self, key: str, value: str) -> None:
        values = self._read()
        value = str(value or "").strip()
        if value:
            values[key] = value
        else:
            values.pop(key, None)
        self._write(values)

    def migrate_from_config(self, provider_data: dict[str, dict]) -> bool:
        values = self._read()
        changed = False
        for provider_id in ("gemini", "groq", "openrouter"):
            provider = provider_data.get(provider_id) or {}
            api_key = str(provider.get("api_key", "") or "").strip()
            secret_key = f"{provider_id}_api_key"
            if api_key and not values.get(secret_key):
                values[secret_key] = api_key
                changed = True
        if changed:
            self._write(values)
        return changed
