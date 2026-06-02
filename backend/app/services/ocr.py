"""Azure AI Vision OCR service."""

from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.services.exceptions import OCRExtractionError


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
    """OCR service backed by Azure AI Vision."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self.endpoint,
            headers={"Ocp-Apim-Subscription-Key": key},
            timeout=timeout_seconds,
        )

    async def extract_text(self, image_bytes: bytes, content_type: str) -> OCRResult:
        """Extract text from an uploaded label image with Azure AI Vision."""
        _ = content_type

        try:
            response = await self._client.post(
                "/computervision/imageanalysis:analyze",
                params={"api-version": "2024-02-01", "features": "read"},
                content=image_bytes,
                headers={"Content-Type": "application/octet-stream"},
            )
        except httpx.TimeoutException as exc:
            raise OCRExtractionError("Azure AI Vision unavailable") from exc
        except httpx.HTTPError as exc:
            raise OCRExtractionError("Azure AI Vision unavailable") from exc

        if response.status_code == 429:
            raise OCRExtractionError("Azure AI Vision rate limit exceeded")
        if 400 <= response.status_code < 500:
            raise OCRExtractionError("Azure AI Vision rejected the request")
        if response.status_code >= 500:
            raise OCRExtractionError("Azure AI Vision unavailable")

        try:
            payload = response.json()
        except ValueError as exc:
            raise OCRExtractionError(
                "Azure AI Vision returned an invalid response"
            ) from exc

        return _parse_azure_read_result(payload)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def _parse_azure_read_result(payload: dict[str, Any]) -> OCRResult:
    """Parse Azure AI Vision read output into OCRResult."""
    try:
        blocks = payload.get("readResult", {}).get("blocks", [])
    except AttributeError as exc:
        raise OCRExtractionError(
            "Azure AI Vision returned an invalid response"
        ) from exc

    if not isinstance(blocks, list):
        raise OCRExtractionError("Azure AI Vision returned an invalid response")

    lines: list[OCRLine] = []
    word_confidences: list[float] = []

    for block in blocks:
        if not isinstance(block, dict):
            raise OCRExtractionError("Azure AI Vision returned an invalid response")

        raw_lines = block.get("lines", [])
        if not isinstance(raw_lines, list):
            raise OCRExtractionError("Azure AI Vision returned an invalid response")

        for line in raw_lines:
            if not isinstance(line, dict):
                raise OCRExtractionError("Azure AI Vision returned an invalid response")

            text = line.get("text", "")
            if not isinstance(text, str) or not text:
                continue

            words = line.get("words", [])
            if not isinstance(words, list):
                raise OCRExtractionError("Azure AI Vision returned an invalid response")

            confidences = [
                float(word["confidence"])
                for word in words
                if isinstance(word, dict) and word.get("confidence") is not None
            ]
            word_confidences.extend(confidences)

            line_confidence = (
                sum(confidences) / len(confidences)
                if confidences
                else float(line.get("confidence", 0.0) or 0.0)
            )
            polygon = _parse_bounding_polygon(line.get("boundingPolygon", []))

            lines.append(
                OCRLine(
                    text=text,
                    confidence=line_confidence,
                    bounding_polygon=polygon,
                )
            )

    if not lines:
        return OCRResult(
            text="",
            lines=[],
            average_confidence=0.0,
            image_quality_issues=["no_text_detected"],
        )

    if word_confidences:
        average_confidence = sum(word_confidences) / len(word_confidences)
    else:
        average_confidence = sum(line.confidence for line in lines) / len(lines)

    issues: list[str] = []
    if average_confidence < 0.70:
        issues.append("low_confidence")

    return OCRResult(
        text="\n".join(line.text for line in lines),
        lines=lines,
        average_confidence=average_confidence,
        image_quality_issues=issues,
    )


def _parse_bounding_polygon(raw_polygon: list[Any]) -> list[Point]:
    """Parse Azure bounding polygon formats into Point objects."""
    if not isinstance(raw_polygon, list):
        raise OCRExtractionError("Azure AI Vision returned an invalid response")

    points: list[Point] = []

    for point in raw_polygon:
        if isinstance(point, dict):
            x = point.get("x")
            y = point.get("y")
            if x is not None and y is not None:
                points.append(Point(x=float(x), y=float(y)))
        elif isinstance(point, (list, tuple)) and len(point) == 2:
            points.append(Point(x=float(point[0]), y=float(point[1])))

    return points
