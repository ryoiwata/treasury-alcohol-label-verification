"""Tests for Azure AI Vision OCR service."""

import os
from io import BytesIO

import httpx
import pytest
import respx
from PIL import Image

from app.services.exceptions import OCRExtractionError
from app.services.ocr import OCRService

AZURE_ENDPOINT = "https://example.cognitiveservices.azure.com"


def make_png_bytes() -> bytes:
    """Create a tiny valid PNG for tests."""
    image = Image.new("RGB", (10, 10), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_success() -> None:
    route = respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(
            200,
            json={
                "readResult": {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "text": "OLD TOM DISTILLERY",
                                    "words": [
                                        {"text": "OLD", "confidence": 0.98},
                                        {"text": "TOM", "confidence": 0.96},
                                    ],
                                    "boundingPolygon": [
                                        {"x": 0, "y": 0},
                                        {"x": 10, "y": 0},
                                    ],
                                },
                                {
                                    "text": "750 mL",
                                    "words": [{"text": "750", "confidence": 0.94}],
                                    "boundingPolygon": [],
                                },
                            ]
                        }
                    ]
                }
            },
        )
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        result = await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()

    assert route.called
    assert result.text == "OLD TOM DISTILLERY\n750 mL"
    assert len(result.lines) == 2
    assert result.average_confidence > 0.90
    assert result.image_quality_issues == []
    assert result.lines[0].bounding_polygon[0].x == 0


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_low_confidence() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(
            200,
            json={
                "readResult": {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "text": "BLURRY TEXT",
                                    "words": [{"text": "BLURRY", "confidence": 0.50}],
                                }
                            ]
                        }
                    ]
                }
            },
        )
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        result = await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()

    assert "low_confidence" in result.image_quality_issues


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_empty_result() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(200, json={"readResult": {"blocks": []}})
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        result = await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()

    assert result.text == ""
    assert result.average_confidence == 0.0
    assert result.image_quality_issues == ["no_text_detected"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403])
@respx.mock
async def test_extract_text_client_error(status_code: int) -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(status_code, json={"error": {"message": "bad"}})
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        with pytest.raises(OCRExtractionError, match="rejected"):
            await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_rate_limit() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate limit"}})
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        with pytest.raises(OCRExtractionError, match="rate limit"):
            await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_server_error() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(500, json={"error": {"message": "server error"}})
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        with pytest.raises(OCRExtractionError, match="unavailable"):
            await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_timeout() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        with pytest.raises(OCRExtractionError, match="unavailable"):
            await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_invalid_json() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(200, text="not json")
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        with pytest.raises(OCRExtractionError, match="invalid response"):
            await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_text_invalid_response_shape() -> None:
    respx.post(f"{AZURE_ENDPOINT}/computervision/imageanalysis:analyze").mock(
        return_value=httpx.Response(200, json={"readResult": {"blocks": "bad"}})
    )

    service = OCRService(endpoint=AZURE_ENDPOINT, key="dummy")
    try:
        with pytest.raises(OCRExtractionError, match="invalid response"):
            await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ocr_real_azure() -> None:
    endpoint = os.getenv("AZURE_VISION_ENDPOINT")
    key = os.getenv("AZURE_VISION_KEY")

    if not endpoint or not key:
        pytest.skip("AZURE_VISION_ENDPOINT and AZURE_VISION_KEY are required")

    service = OCRService(endpoint=endpoint, key=key)
    try:
        result = await service.extract_text(make_png_bytes(), "image/png")
    finally:
        await service.close()

    assert isinstance(result.text, str)
    assert result.average_confidence >= 0.0
