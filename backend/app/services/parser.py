"""GPT parser service backed by OpenAI Chat Completions."""

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.models.schemas import ExtractedFields
from app.services.exceptions import ParserError
from app.utils.constants import (
    FIELD_EXTRACTION_SYSTEM_PROMPT,
    FIELD_EXTRACTION_USER_TEMPLATE,
)


class GPTParser:
    """Parser service backed by GPT-4o."""

    def __init__(self, api_key: str, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout_seconds,
        )

    async def extract_fields(self, ocr_text: str) -> ExtractedFields:
        """Extract structured fields from OCR text using GPT-4o.

        Only OCR text is sent to GPT. Application data is never sent to the
        parser.
        """
        request_body = {
            "model": "gpt-4o",
            "temperature": 0.0,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": FIELD_EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": FIELD_EXTRACTION_USER_TEMPLATE.format(
                        ocr_text=ocr_text,
                    ),
                },
            ],
        }

        try:
            response = await self._client.post(
                "/chat/completions",
                json=request_body,
            )
        except httpx.TimeoutException as exc:
            raise ParserError("OpenAI API unavailable") from exc
        except httpx.HTTPError as exc:
            raise ParserError("OpenAI API unavailable") from exc

        if response.status_code in {401, 403}:
            raise ParserError("OpenAI API authentication failed")
        if response.status_code == 429:
            raise ParserError("OpenAI API rate limit exceeded")
        if 400 <= response.status_code < 500:
            raise ParserError("OpenAI API rejected the request")
        if response.status_code >= 500:
            raise ParserError("OpenAI API unavailable")

        try:
            response_json = response.json()
        except ValueError as exc:
            raise ParserError("OpenAI API returned an invalid response") from exc

        extracted_fields = parse_gpt_extraction(response_json)
        extracted_fields.raw_ocr_text = ocr_text
        return extracted_fields

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def parse_gpt_extraction(response_json: dict[str, Any]) -> ExtractedFields:
    """Parse an OpenAI chat-completion response into extracted fields."""
    if "error" in response_json:
        error = response_json["error"]
        message = error.get("message", "GPT API returned an error")
        raise ParserError(str(message))

    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ParserError("GPT response did not include message content") from exc

    if not isinstance(content, str):
        raise ParserError("GPT response content was not a string")

    try:
        parsed_content = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ParserError("GPT returned non-JSON response") from exc

    if not isinstance(parsed_content, dict):
        raise ParserError("GPT JSON response was not an object")

    try:
        return ExtractedFields.model_validate(parsed_content)
    except ValidationError as exc:
        raise ParserError("GPT JSON response did not match extraction schema") from exc
