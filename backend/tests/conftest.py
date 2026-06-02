"""Shared test fixtures for TTB Label Verification backend tests."""

import json
from collections.abc import Generator
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.utils.constants import GOVERNMENT_WARNING_TEXT


@pytest.fixture
def api_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy environment variables required by app startup."""
    monkeypatch.setenv("AZURE_VISION_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("AZURE_VISION_KEY", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")


@pytest.fixture
def test_client(api_env: None) -> Generator[TestClient, None, None]:
    """Create a TestClient with app lifespan enabled."""
    _ = api_env
    with TestClient(app) as client:
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
