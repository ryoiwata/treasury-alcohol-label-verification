"""Tests for text normalization and numeric extraction helpers."""

import pytest

from app.utils.normalization import (
    extract_abv_numeric,
    extract_numeric_value,
    extract_volume_ml,
    normalize_for_fuzzy_comparison,
    normalize_string,
    normalize_unicode_punctuation,
    normalize_whitespace,
    strip_punctuation,
)


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("  hello   world  ", "hello world"),
        ("hello\n\nworld", "hello world"),
        ("hello\tworld", "hello world"),
        (" hello \r\n world ", "hello world"),
        ("", ""),
    ],
)
def test_normalize_whitespace(input_text: str, expected: str) -> None:
    assert normalize_whitespace(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("‘quoted’", "'quoted'"),
        ("“quoted”", '"quoted"'),
        ("a – b", "a - b"),
        ("a — b", "a - b"),
        ("etc…", "etc..."),
        ("STONE’S THROW", "STONE'S THROW"),
    ],
)
def test_normalize_unicode_punctuation(input_text: str, expected: str) -> None:
    assert normalize_unicode_punctuation(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("STONE’S THROW", "stone's throw"),
        ("  OLD   TOM\nDISTILLERY  ", "old tom distillery"),
        ("Kentucky—Straight", "kentucky-straight"),
    ],
)
def test_normalize_for_fuzzy_comparison(input_text: str, expected: str) -> None:
    assert normalize_for_fuzzy_comparison(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("45% Alc./Vol. (90 Proof)", 45.0),
        ("13.5%", 13.5),
        ("90 Proof", 45.0),
        ("90 proof", 45.0),
        ("45", 45.0),
        ("no numbers here", None),
    ],
)
def test_extract_abv_numeric(input_text: str, expected: float | None) -> None:
    assert extract_abv_numeric(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("750 mL", 750.0),
        ("750ml", 750.0),
        ("1 L", 1000.0),
        ("1.75L", 1750.0),
        ("375 ML", 375.0),
        ("no numbers here", None),
    ],
)
def test_extract_volume_ml(input_text: str, expected: float | None) -> None:
    assert extract_volume_ml(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("25.4 fl oz", pytest.approx(751.1669)),
        ("12 oz", pytest.approx(354.882)),
        ("12 FL. OZ", pytest.approx(354.882)),
    ],
)
def test_extract_volume_ml_fluid_ounces(input_text: str, expected: float) -> None:
    assert extract_volume_ml(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("45% Alc./Vol. (90 Proof)", 45.0),
        ("13.5%", 13.5),
        ("90 Proof", 45.0),
        ("750 mL", 750.0),
        ("1 L", 1000.0),
        ("123", 123.0),
        ("no numbers here", None),
    ],
)
def test_extract_numeric_value(input_text: str, expected: float | None) -> None:
    assert extract_numeric_value(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("Hello, world!", "Hello world"),
        ("STONE'S THROW", "STONES THROW"),
        ("Kentucky-Straight Bourbon", "KentuckyStraight Bourbon"),
    ],
)
def test_strip_punctuation(input_text: str, expected: str) -> None:
    assert strip_punctuation(input_text) == expected


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        ("  Kentucky Straight   Bourbon Whiskey ", "kentucky straight bourbon whiskey"),
        ("STONE’S THROW", "stones throw"),
        ("Imported-from France", "importedfrom france"),
        ("hello,   world!", "hello world"),
    ],
)
def test_normalize_string(input_text: str, expected: str) -> None:
    assert normalize_string(input_text) == expected
