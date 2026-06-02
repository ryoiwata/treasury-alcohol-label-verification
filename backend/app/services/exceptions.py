"""Domain-specific service exceptions."""


class OCRExtractionError(Exception):
    """Raised when OCR extraction fails."""


class ParserError(Exception):
    """Raised when GPT field extraction fails or returns unparseable output."""


class InvalidImageError(ValueError):
    """Raised when an uploaded file fails validation."""
