import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ApplicationData,
    BatchStatus,
    ExtractedFields,
    FieldComparison,
    HistoryResponse,
    ImageQuality,
    VerificationResult,
)
from app.utils.constants import GOVERNMENT_WARNING_TEXT


def make_application_data() -> dict[str, str]:
    """Return valid sample application data."""
    return {
        "brand_name": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv": "45",
        "net_contents": "750 mL",
        "warning_statement": GOVERNMENT_WARNING_TEXT,
        "producer": "Old Tom Distillery, Louisville, KY",
        "origin": "United States",
    }


def make_field_comparison() -> FieldComparison:
    """Return a valid sample field comparison."""
    return FieldComparison(
        field="brand_name",
        status="MATCH",
        extracted="OLD TOM DISTILLERY",
        expected="OLD TOM DISTILLERY",
        confidence=0.98,
        method="fuzzy_match",
        similarity=1.0,
        note="Exact match after normalization",
    )


def make_verification_result() -> VerificationResult:
    """Return a valid sample verification result."""
    return VerificationResult(
        id="ver_test123",
        status="PASS",
        processing_time_ms=1250,
        fields=[make_field_comparison()],
        image_quality=ImageQuality(readable=True, issues=[]),
    )


def test_application_data_valid() -> None:
    data = ApplicationData(**make_application_data())

    assert data.brand_name == "OLD TOM DISTILLERY"
    assert data.warning_statement == GOVERNMENT_WARNING_TEXT
    assert data.producer == "Old Tom Distillery, Louisville, KY"
    assert data.origin == "United States"


def test_application_data_missing_required() -> None:
    with pytest.raises(ValidationError):
        ApplicationData(brand_name="", abv="45")


def test_application_data_extra_forbidden() -> None:
    payload = make_application_data()
    payload["unexpected_field"] = "not allowed"

    with pytest.raises(ValidationError):
        ApplicationData(**payload)


def test_extracted_fields_allows_missing_values() -> None:
    fields = ExtractedFields()

    assert fields.brand_name is None
    assert fields.class_type is None
    assert fields.abv is None
    assert fields.net_contents is None
    assert fields.warning_statement is None
    assert fields.producer is None
    assert fields.origin is None
    assert fields.raw_ocr_text is None


def test_field_comparison_validates_literals() -> None:
    comparison = make_field_comparison()

    assert comparison.status == "MATCH"
    assert comparison.method == "fuzzy_match"

    with pytest.raises(ValidationError):
        FieldComparison(
            field="brand_name",
            status="INVALID",
            extracted="OLD TOM DISTILLERY",
            expected="OLD TOM DISTILLERY",
            method="fuzzy_match",
        )

    with pytest.raises(ValidationError):
        FieldComparison(
            field="brand_name",
            status="MATCH",
            extracted="OLD TOM DISTILLERY",
            expected="OLD TOM DISTILLERY",
            method="invalid_method",
        )


def test_verification_result_serialization() -> None:
    result = make_verification_result()

    json_payload = result.model_dump_json()
    reloaded = VerificationResult.model_validate_json(json_payload)

    assert reloaded.status == "PASS"
    assert reloaded.fields[0].status == "MATCH"
    assert reloaded.fields[0].method == "fuzzy_match"


def test_batch_status_and_history_response_shapes() -> None:
    result = make_verification_result()
    batch_status = BatchStatus(
        batch_id="bat_test123",
        status="complete",
        total=1,
        completed=1,
        results=[result],
    )
    history_response = HistoryResponse(
        total=1,
        limit=20,
        offset=0,
        results=[result],
    )

    assert batch_status.results is not None
    assert batch_status.results[0].id == "ver_test123"
    assert history_response.results[0].fields[0].method == "fuzzy_match"
