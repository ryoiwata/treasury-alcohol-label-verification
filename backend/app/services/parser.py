"""GPT parser interface and deterministic Phase 5 stub."""

import json
from typing import Any

from pydantic import ValidationError

from app.models.schemas import ExtractedFields
from app.services.exceptions import ParserError
from app.utils.constants import GOVERNMENT_WARNING_TEXT


class GPTParser:
    """Parser service interface.

    Phase 5 returns deterministic stub data. Phase 8 replaces this with GPT-4o.
    """

    def __init__(self, api_key: str, timeout_seconds: float = 60.0) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def extract_fields(self, ocr_text: str) -> ExtractedFields:
        """Extract structured fields from OCR text.

        STUB: Phase 5 ignores OCR text and returns deterministic fields. Phase 8
        will call GPT-4o here. Application data must never be sent to GPT.
        """
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

    async def close(self) -> None:
        """Close any held resources.

        STUB: no resources are opened in Phase 5.
        """


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
