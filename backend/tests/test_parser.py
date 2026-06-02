"""Tests for GPT parser response parsing."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.exceptions import ParserError
from app.services.parser import parse_gpt_extraction

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gpt_responses"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a GPT response fixture."""
    with (FIXTURES_DIR / name).open() as fixture_file:
        data: dict[str, Any] = json.load(fixture_file)
    return data


def test_parse_gpt_extraction_valid_response() -> None:
    result = parse_gpt_extraction(load_fixture("valid_extraction.json"))

    assert result.brand_name == "OLD TOM DISTILLERY"
    assert result.class_type == "Kentucky Straight Bourbon Whiskey"
    assert result.abv == "45% Alc./Vol. (90 Proof)"
    assert result.net_contents == "750 mL"
    assert result.warning_statement is not None
    assert result.producer is not None


def test_parse_gpt_extraction_partial_response() -> None:
    result = parse_gpt_extraction(load_fixture("partial_extraction.json"))

    assert result.brand_name == "OLD TOM DISTILLERY"
    assert result.producer is None
    assert result.origin is None


def test_parse_gpt_extraction_malformed_response() -> None:
    with pytest.raises(ParserError, match="non-JSON"):
        parse_gpt_extraction(load_fixture("malformed_response.json"))


def test_parse_gpt_extraction_error_response() -> None:
    with pytest.raises(ParserError, match="Rate limit"):
        parse_gpt_extraction(load_fixture("error_response.json"))


def test_parse_gpt_extraction_missing_content() -> None:
    with pytest.raises(ParserError, match="message content"):
        parse_gpt_extraction({"choices": [{}]})
