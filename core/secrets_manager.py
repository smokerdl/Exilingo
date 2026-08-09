from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = PROJECT_ROOT / "secrets.txt"


class SecretsManager:
    """Local-only storage for API keys and other provider secrets."""

    def __init__(self, filename: str | Path = SECRETS_FILE):
        self.filename = Path(filename)
        if not self.filename.is_absolute():
            self.filename = PROJECT_ROOT / self.filename
        self._ensure_file()

    def _ensure_file(self) -> None:
        if self.filename.exists():
            return
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.filename.write_text(
            "# Exilingo local secrets - DO NOT COMMIT\n"
            "gemini_api_key=\n"
            "groq_api_key=\n"
            "openrouter_api_key=\n",
            encoding="utf-8",
        )

    def _read(self) -> dict[str, str]:
        values: dict[str, str] = {}
        try:
            for raw_line in self.filename.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        except OSError:
            pass
        return values

    def _write(self, values: dict[str, str]) -> None:
        lines = ["# Exilingo local secrets - DO NOT COMMIT"]
        known = {"gemini_api_key", "groq_api_key", "openrouter_api_key"}
        for key in ("gemini_api_key", "groq_api_key", "openrouter_api_key"):
            lines.append(f"{key}={values.get(key, '')}")
        for key, value in values.items():
            if key not in known:
                lines.append(f"{key}={value}")
        self.filename.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def get(self, provider_id: str) -> str:
        return self._read().get(f"{provider_id}_api_key", "")

    def set(self, provider_id: str, value: str) -> None:
        values = self._read()
        values[f"{provider_id}_api_key"] = str(value or "").strip()
        self._write(values)

    def configured(self, provider_id: str) -> bool:
        return bool(self.get(provider_id))


secrets = SecretsManager()
