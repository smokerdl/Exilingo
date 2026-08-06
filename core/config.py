import json
import os
from copy import deepcopy


CONFIG_FILE = "config.json"


DEFAULT_CONFIG = {
    "log_path": "",
    "overlay_geometry": {
        "x": 1,
        "y": 11,
        "w": 700,
        "h": 309,
    },
    "font_size": 13,
    "translation": {
        "provider": "google",
        "source_language": "en",
        "target_language": "ru",
    },
}


class Config:
    """
    Централизованная работа с config.json.

    Весь проект обращается только к этому объекту.
    """

    def __init__(self, filename: str = CONFIG_FILE):

        self.filename = filename

        self.data = deepcopy(DEFAULT_CONFIG)

        self.load()

    # =====================================================
    # Загрузка
    # =====================================================

    def load(self):

        if not os.path.exists(self.filename):
            self.save()
            return

        try:
            with open(
                self.filename,
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
            with open(
                self.filename,
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
    # Обновление словаря
    # =====================================================

    def _merge_dict(
        self,
        default,
        loaded,
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
    # Общие методы
    # =====================================================

    def get(
        self,
        key,
        default=None,
    ):

        return self.data.get(
            key,
            default,
        )

    def set(
        self,
        key,
        value,
    ):

        self.data[key] = value

        self.save()

    # =====================================================
    # Свойства
    # =====================================================

    @property
    def log_path(self):

        return self.data["log_path"]

    @log_path.setter
    def log_path(
        self,
        value,
    ):

        self.data["log_path"] = value

        self.save()

    # -----------------------------------------------------

    @property
    def overlay_geometry(self):

        return self.data["overlay_geometry"]

    @overlay_geometry.setter
    def overlay_geometry(
        self,
        value,
    ):

        self.data["overlay_geometry"] = value

        self.save()

    # -----------------------------------------------------

    @property
    def font_size(self):

        return self.data["font_size"]

    @font_size.setter
    def font_size(
        self,
        value,
    ):

        self.data["font_size"] = value

        self.save()

    # -----------------------------------------------------

    @property
    def translation(self):

        return self.data["translation"]

    @property
    def provider(self):

        return self.data["translation"]["provider"]

    @property
    def source_language(self):

        return self.data["translation"]["source_language"]

    @property
    def target_language(self):

        return self.data["translation"]["target_language"]


# =========================================================
# Глобальный объект конфигурации
# =========================================================

config = Config()
