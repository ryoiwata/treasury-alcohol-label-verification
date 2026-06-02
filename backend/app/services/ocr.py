"""OCR service interface and deterministic Phase 5 stub."""

from pydantic import BaseModel, Field

from app.utils.constants import GOVERNMENT_WARNING_TEXT


class Point(BaseModel):
    """A point in image coordinate space."""

    x: float
    y: float


class OCRLine(BaseModel):
    """One OCR line with confidence and optional polygon data."""

    text: str
    confidence: float
    bounding_polygon: list[Point] = Field(default_factory=list)


class OCRResult(BaseModel):
    """Structured OCR output consumed by the parser."""

    text: str
    lines: list[OCRLine] = Field(default_factory=list)
    average_confidence: float = 0.0
    image_quality_issues: list[str] = Field(default_factory=list)


class OCRService:
    """OCR service interface.

    Phase 5 returns deterministic stub data. Phase 7 replaces this with Azure AI
    Vision.
    """

    def __init__(
        self,
        endpoint: str,
        key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.endpoint = endpoint
        self.key = key
        self.timeout_seconds = timeout_seconds

    async def extract_text(self, image_bytes: bytes, content_type: str) -> OCRResult:
        """Extract text from an uploaded label image.

        STUB: Phase 5 ignores the image bytes and content type. Phase 7 will call
        Azure AI Vision here.
        """
        _ = image_bytes
        _ = content_type

        lines = [
            OCRLine(text="OLD TOM DISTILLERY", confidence=0.98),
            OCRLine(text="Kentucky Straight Bourbon Whiskey", confidence=0.97),
            OCRLine(text="45% Alc./Vol. (90 Proof)", confidence=0.96),
            OCRLine(text="750 mL", confidence=0.99),
            OCRLine(text="Bottled by Old Tom Distillery", confidence=0.95),
            OCRLine(text="Louisville, Kentucky", confidence=0.95),
            OCRLine(text=GOVERNMENT_WARNING_TEXT, confidence=0.93),
        ]

        return OCRResult(
            text="\n".join(line.text for line in lines),
            lines=lines,
            average_confidence=0.96,
            image_quality_issues=[],
        )

    async def close(self) -> None:
        """Close any held resources.

        STUB: no resources are opened in Phase 5.
        """
