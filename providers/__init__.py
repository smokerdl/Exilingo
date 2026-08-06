"""
Пакет провайдеров перевода Exilingo.

Каждый провайдер реализует интерфейс BaseTranslator
и может быть подключен к TranslationManager без
изменения остального кода приложения.
"""

from .base import BaseTranslator
from .google_translate import GoogleTranslateTranslator

__all__ = [
    "BaseTranslator",
    "GoogleTranslateTranslator",
]
