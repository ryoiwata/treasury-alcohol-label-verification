"""Shared test fixtures for TTB Label Verification backend tests."""

import json
from collections.abc import Generator
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.models.schemas import ExtractedFields
from app.services.comparator import Comparator, ComparisonConfig
from app.services.ocr import OCRLine, OCRResult
from app.services.pipeline import VerificationPipeline
from app.utils.constants import GOVERNMENT_WARNING_TEXT


class StubOCRService:
    """Offline OCR stub for API tests."""

    async def extract_text(self, image_bytes: bytes, content_type: str) -> OCRResult:
        """Return deterministic OCR text without network access."""
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


class StubGPTParser:
    """Offline parser stub for API tests."""

    async def extract_fields(self, ocr_text: str) -> ExtractedFields:
        """Return deterministic extracted fields without API access."""
        return ExtractedFields(
            brand_name="OLD TOM DISTILLERY",
            class_type="Kentucky Straight Bourbon Whiskey",
            abv="45% Alc./Vol. (90 Proof)",
            net_contents="750 mL",
            warning_statement=GOVERNMENT_WARNING_TEXT,
            producer="Bottled by Old Tom Distillery, Louisville, Kentucky",
            origin=None,
            raw_ocr_text=ocr_text,
        )


@pytest.fixture
def api_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy environment variables required by app startup."""
    monkeypatch.setenv("AZURE_VISION_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_VISION_KEY", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")


@pytest.fixture
def test_client(api_env: None) -> Generator[TestClient, None, None]:
    """Create a TestClient with app lifespan enabled and offline services."""
    _ = api_env
    with TestClient(app) as client:
        client.app.state.pipeline = VerificationPipeline(
            ocr=StubOCRService(),
            parser=StubGPTParser(),
            comparator=Comparator(ComparisonConfig()),
        )
        yield client


@pytest.fixture
def valid_png_bytes() -> bytes:
    """Return a tiny valid PNG image."""
    image = Image.new("RGB", (1, 1), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def application_data_payload() -> dict[str, Any]:
    """Return matching sample application data."""
    return {
        "brand_name": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv": "45%",
        "net_contents": "750 mL",
        "warning_statement": GOVERNMENT_WARNING_TEXT,
        "producer": "Bottled by Old Tom Distillery, Louisville, Kentucky",
        "origin": None,
    }


@pytest.fixture
def application_data_json(application_data_payload: dict[str, Any]) -> str:
    """Return matching sample application data as JSON."""
    return json.dumps(application_data_payload)
