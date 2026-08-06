from abc import ABC, abstractmethod


class BaseTranslator(ABC):
    """
    Базовый интерфейс любого переводчика.

    Все провайдеры обязаны реализовать
    только один метод translate().
    """

    @abstractmethod
    def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """
        Перевод строки.

        Parameters
        ----------
        text
            Исходный текст.

        source_language
            Код языка (например "en", "ru", "auto").

        target_language
            Код языка назначения.

        Returns
        -------
        str
            Переведённый текст.
        """
        raise NotImplementedError
