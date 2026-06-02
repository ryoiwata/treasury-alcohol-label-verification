"""Tests for the deterministic verification pipeline."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.models.schemas import ApplicationData
from app.services.comparator import Comparator, ComparisonConfig
from app.services.ocr import OCRService
from app.services.parser import GPTParser
from app.services.pipeline import VerificationPipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "application_data"


def load_application_data(name: str) -> ApplicationData:
    """Load an application data fixture."""
    with (FIXTURES_DIR / name).open() as fixture_file:
        data: dict[str, Any] = json.load(fixture_file)
    return ApplicationData.model_validate(data)


@pytest.fixture
def pipeline() -> VerificationPipeline:
    return VerificationPipeline(
        ocr=OCRService(endpoint="https://example.invalid", key="dummy"),
        parser=GPTParser(api_key="dummy"),
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
