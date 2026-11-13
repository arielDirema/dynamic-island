"""Exceptions raised by the localization subsystem."""


class LocalizationError(Exception):
    """Base class for localization failures."""


class CatalogError(LocalizationError):
    """A locale catalog is missing, malformed, or incomplete."""


class UnsupportedLanguageError(LocalizationError):
    """The requested language is not available."""

    def __init__(self, language: str, available: list[str]):
        self.language = language
        self.available = available
        super().__init__(
            f"Unsupported language {language!r}; available languages: {', '.join(available) or 'none'}"
        )
