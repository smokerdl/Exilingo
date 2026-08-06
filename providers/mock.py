import time

from .base import BaseTranslator


class MockTranslator(BaseTranslator):
    """
    Временный переводчик.

    Используется для проверки всего Translation Pipeline
    без обращения к внешним API.
    """

    def translate(self, text: str) -> str:
        # Имитация задержки сети

        time.sleep(0.2)

        return f"[RU] {text}"
