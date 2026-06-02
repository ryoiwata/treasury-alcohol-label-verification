"""Tests for the deterministic verification pipeline."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.models.schemas import ApplicationData, ExtractedFields
from app.services.comparator import Comparator, ComparisonConfig
from app.services.ocr import OCRLine, OCRResult
from app.services.pipeline import VerificationPipeline
from app.utils.constants import GOVERNMENT_WARNING_TEXT

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "application_data"


def load_application_data(name: str) -> ApplicationData:
    """Load an application data fixture."""
    with (FIXTURES_DIR / name).open() as fixture_file:
        data: dict[str, Any] = json.load(fixture_file)
    return ApplicationData.model_validate(data)


class StubOCRService:
    """Offline OCR stub for pipeline tests."""

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
    """Offline parser stub for pipeline tests."""

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
def pipeline() -> VerificationPipeline:
    return VerificationPipeline(
        ocr=StubOCRService(),
        parser=StubGPTParser(),
        comparator=Comparator(ComparisonConfig()),
    )


@pytest.mark.asyncio
async def test_pipeline_verify_matching_application(
    pipeline: VerificationPipeline,
) -> None:
    application_data = load_application_data("bourbon_application.json")

    result = await pipeline.verify(
        image_bytes=b"fake image bytes",
        content_type="image/png",
        application_data=application_data,
    )

    assert result.id.startswith("ver_")
    assert result.processing_time_ms >= 0
    assert result.status in {"PASS", "REVIEW_NEEDED", "FAIL"}
    assert result.status == "PASS"
    assert result.fields
    assert result.image_quality.readable is True


@pytest.mark.asyncio
async def test_pipeline_verify_mismatch_application(
    pipeline: VerificationPipeline,
) -> None:
    application_data = load_application_data("mismatch_application.json")

    result = await pipeline.verify(
        image_bytes=b"fake image bytes",
        content_type="image/png",
        application_data=application_data,
    )

    assert result.id.startswith("ver_")
    assert result.processing_time_ms >= 0
    assert result.status == "FAIL"
    assert result.fields
    assert result.image_quality.readable is True
