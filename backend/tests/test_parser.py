"""Tests for GPT parser response parsing and HTTP integration."""

import json
import os
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.models.schemas import ExtractedFields
from app.services.exceptions import ParserError
from app.services.parser import GPTParser, parse_gpt_extraction

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gpt_responses"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


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


@pytest.mark.asyncio
@respx.mock
async def test_extract_fields_success_sets_raw_ocr_text() -> None:
    ocr_text = "OLD TOM DISTILLERY\n45% Alc./Vol. (90 Proof)\n750 mL"
    route = respx.post(OPENAI_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, json=load_fixture("valid_extraction.json"))
    )

    parser = GPTParser(api_key="dummy")
    try:
        result = await parser.extract_fields(ocr_text)
    finally:
        await parser.close()

    assert route.called
    assert result.brand_name == "OLD TOM DISTILLERY"
    assert result.raw_ocr_text == ocr_text

    request = route.calls.last.request
    body = json.loads(request.content)

    assert body["model"] == "gpt-4o"
    assert body["temperature"] == 0.0
    assert body["response_format"] == {"type": "json_object"}
    assert ocr_text in body["messages"][1]["content"]
    serialized_body = json.dumps(body)
    assert "application_data" not in serialized_body
    assert "expected" not in serialized_body
    assert "COMPLETELY DIFFERENT BRAND" not in serialized_body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "message"),
    [
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate limit"),
        (400, "rejected"),
        (500, "unavailable"),
    ],
)
@respx.mock
async def test_extract_fields_http_errors(status_code: int, message: str) -> None:
    respx.post(OPENAI_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(status_code, json={"error": {"message": "bad"}})
    )

    parser = GPTParser(api_key="dummy")
    try:
        with pytest.raises(ParserError, match=message):
            await parser.extract_fields("OCR text")
    finally:
        await parser.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_fields_invalid_json_response() -> None:
    respx.post(OPENAI_CHAT_COMPLETIONS_URL).mock(
        return_value=httpx.Response(200, text="not json")
    )

    parser = GPTParser(api_key="dummy")
    try:
        with pytest.raises(ParserError, match="invalid response"):
            await parser.extract_fields("OCR text")
    finally:
        await parser.close()


@pytest.mark.asyncio
@respx.mock
async def test_extract_fields_timeout() -> None:
    respx.post(OPENAI_CHAT_COMPLETIONS_URL).mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    parser = GPTParser(api_key="dummy")
    try:
        with pytest.raises(ParserError, match="unavailable"):
            await parser.extract_fields("OCR text")
    finally:
        await parser.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parser_real_openai() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY is required")

    parser = GPTParser(api_key=api_key)
    try:
        result = await parser.extract_fields(
            "OLD TOM DISTILLERY\n"
            "Kentucky Straight Bourbon Whiskey\n"
            "45% Alc./Vol. (90 Proof)\n"
            "750 mL"
        )
    finally:
        await parser.close()

    assert isinstance(result, ExtractedFields)
