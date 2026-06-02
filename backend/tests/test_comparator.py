"""Tests for the deterministic comparison engine."""

import pytest

from app.models.schemas import ApplicationData, ExtractedFields, FieldComparison
from app.services.comparator import (
    Comparator,
    ComparisonConfig,
    compare_abv,
    compare_brand_name,
    compare_net_contents,
    compare_text_field,
    compare_warning_statement,
    derive_overall_status,
)
from app.utils.constants import GOVERNMENT_WARNING_TEXT


@pytest.fixture
def comparator() -> Comparator:
    return Comparator(ComparisonConfig())


@pytest.mark.parametrize(
    ("extracted", "expected", "expected_status"),
    [
        (GOVERNMENT_WARNING_TEXT, GOVERNMENT_WARNING_TEXT, "MATCH"),
        (
            GOVERNMENT_WARNING_TEXT.replace(
                "GOVERNMENT WARNING:",
                "Government Warning:",
            ),
            GOVERNMENT_WARNING_TEXT,
            "MISMATCH",
        ),
        (GOVERNMENT_WARNING_TEXT.replace(" ", "   "), GOVERNMENT_WARNING_TEXT, "MATCH"),
        ("", GOVERNMENT_WARNING_TEXT, "NOT_FOUND"),
        (None, GOVERNMENT_WARNING_TEXT, "NOT_FOUND"),
        (
            "GOVERNMENT WARNING: (1) According to the Surgeon General",
            GOVERNMENT_WARNING_TEXT,
            "MISMATCH",
        ),
    ],
)
def test_compare_warning_statement(
    extracted: str | None,
    expected: str,
    expected_status: str,
) -> None:
    result = compare_warning_statement(extracted, expected)

    assert result.field == "warning_statement"
    assert result.method == "exact_match"
    assert result.status == expected_status


@pytest.mark.parametrize(
    ("extracted", "expected", "expected_status"),
    [
        ("STONE'S THROW", "Stone's Throw", "MATCH"),
        ("stone's throw", "Stone's Throw", "MATCH"),
        ("OLD TOM DISTILLERV", "OLD TOM DISTILLERY", "WARNING"),
        ("STONE’S THROW", "Stone's Throw", "MATCH"),
        ("STONE THROW", "Stone's Throw", "WARNING"),
        ("OLD TOM DISTILLERY", "Stone's Throw", "MISMATCH"),
        ("", "Stone's Throw", "NOT_FOUND"),
        (None, "Stone's Throw", "NOT_FOUND"),
    ],
)
def test_compare_brand_name(
    extracted: str | None,
    expected: str,
    expected_status: str,
) -> None:
    result = compare_brand_name(extracted, expected)

    assert result.field == "brand_name"
    assert result.method == "fuzzy_match"
    assert result.status == expected_status
    if result.status in {"MATCH", "WARNING", "MISMATCH"}:
        assert result.similarity is not None
        assert 0.0 <= result.similarity <= 1.0


@pytest.mark.parametrize(
    ("extracted", "expected", "expected_status"),
    [
        ("45% Alc./Vol. (90 Proof)", "45%", "MATCH"),
        ("13.5%", "13.5", "MATCH"),
        ("90 Proof", "45%", "MATCH"),
        ("44.8%", "45%", "WARNING"),
        ("44.5%", "45%", "WARNING"),
        ("44.4%", "45%", "MISMATCH"),
        ("40%", "45%", "MISMATCH"),
        ("", "45%", "NOT_FOUND"),
        (None, "45%", "NOT_FOUND"),
        ("not readable", "45%", "MISMATCH"),
    ],
)
def test_compare_abv(
    extracted: str | None,
    expected: str,
    expected_status: str,
) -> None:
    result = compare_abv(extracted, expected)

    assert result.field == "abv"
    assert result.method == "numeric_match"
    assert result.status == expected_status


@pytest.mark.parametrize(
    ("extracted", "expected", "expected_status"),
    [
        ("750 mL", "750 mL", "MATCH"),
        ("750ml", "750 mL", "MATCH"),
        ("0.75 L", "750 mL", "MATCH"),
        ("1 L", "1000 mL", "MATCH"),
        ("375 mL", "750 mL", "MISMATCH"),
        ("25.4 fl oz", "750 mL", "MISMATCH"),
        ("", "750 mL", "NOT_FOUND"),
        (None, "750 mL", "NOT_FOUND"),
        ("not readable", "750 mL", "MISMATCH"),
    ],
)
def test_compare_net_contents(
    extracted: str | None,
    expected: str,
    expected_status: str,
) -> None:
    result = compare_net_contents(extracted, expected)

    assert result.field == "net_contents"
    assert result.method == "numeric_match"
    assert result.status == expected_status


@pytest.mark.parametrize(
    ("extracted", "expected", "field_name", "expected_status"),
    [
        (
            "Kentucky Straight Bourbon Whiskey",
            "Kentucky Straight Bourbon Whiskey",
            "class_type",
            "MATCH",
        ),
        (
            "kentucky straight bourbon whiskey",
            "Kentucky Straight Bourbon Whiskey",
            "class_type",
            "MATCH",
        ),
        (
            "Kentucky Straight Bourbon",
            "Kentucky Straight Bourbon Whiskey",
            "class_type",
            "WARNING",
        ),
        ("France", "france", "origin", "MATCH"),
        ("Francee", "France", "origin", "WARNING"),
        ("Spain", "France", "origin", "MISMATCH"),
        ("", "France", "origin", "NOT_FOUND"),
        (None, "France", "origin", "NOT_FOUND"),
    ],
)
def test_compare_text_field(
    extracted: str | None,
    expected: str,
    field_name: str,
    expected_status: str,
) -> None:
    result = compare_text_field(extracted, expected, field_name)

    assert result.field == field_name
    assert result.method == "normalized_match"
    assert result.status == expected_status


def test_compare_all_skips_optional_expected_fields(comparator: Comparator) -> None:
    extracted = ExtractedFields(
        brand_name="STONE'S THROW",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        warning_statement=GOVERNMENT_WARNING_TEXT,
        producer="Some Producer",
        origin="France",
    )
    expected = ApplicationData(
        brand_name="Stone's Throw",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45%",
        net_contents="750 mL",
        warning_statement=GOVERNMENT_WARNING_TEXT,
        producer=None,
        origin=None,
    )

    results = comparator.compare_all(extracted, expected)

    assert [result.field for result in results] == [
        "brand_name",
        "class_type",
        "abv",
        "net_contents",
        "warning_statement",
    ]


def test_compare_all_returns_stable_field_order(comparator: Comparator) -> None:
    extracted = ExtractedFields(
        brand_name="STONE'S THROW",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45%",
        net_contents="750 mL",
        warning_statement=GOVERNMENT_WARNING_TEXT,
        producer="Bottled by Example Producer",
        origin="France",
    )
    expected = ApplicationData(
        brand_name="Stone's Throw",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45%",
        net_contents="750 mL",
        warning_statement=GOVERNMENT_WARNING_TEXT,
        producer="Bottled by Example Producer",
        origin="France",
    )

    results = comparator.compare_all(extracted, expected)

    assert [result.field for result in results] == [
        "brand_name",
        "class_type",
        "abv",
        "net_contents",
        "warning_statement",
        "producer",
        "origin",
    ]


@pytest.mark.parametrize(
    ("statuses", "expected_overall"),
    [
        (["MATCH", "MATCH"], "PASS"),
        (["MATCH", "WARNING"], "REVIEW_NEEDED"),
        (["MATCH", "NOT_FOUND"], "REVIEW_NEEDED"),
        (["MATCH", "MISMATCH"], "FAIL"),
        (["WARNING", "MISMATCH"], "FAIL"),
    ],
)
def test_derive_overall_status(
    statuses: list[str],
    expected_overall: str,
) -> None:
    field_results = [
        FieldComparison(
            field=f"field_{index}",
            status=status,
            extracted="x",
            expected="x",
            method="exact_match",
        )
        for index, status in enumerate(statuses)
    ]

    assert derive_overall_status(field_results) == expected_overall
