"""Deterministic field comparison engine.

This module is intentionally pure Python. It performs no I/O, no network calls,
no database access, and no LLM calls. The comparison engine is the auditable
compliance boundary for label verification.
"""

import math
from dataclasses import dataclass
from typing import Literal

from fuzzywuzzy import fuzz

from app.models.schemas import ApplicationData, ExtractedFields, FieldComparison
from app.utils.constants import FIELD_STRATEGIES
from app.utils.normalization import (
    extract_abv_numeric,
    extract_volume_ml,
    normalize_for_fuzzy_comparison,
    normalize_string,
    normalize_whitespace,
)


@dataclass
class ComparisonConfig:
    """Configurable thresholds for field comparison."""

    match_threshold: float = 0.95
    warning_threshold: float = 0.85
    abv_tolerance: float = 0.5
    normalize_case: bool = True
    normalize_whitespace: bool = True
    normalize_punctuation: bool = True


@dataclass
class ComparisonResult:
    """Output of a single field comparison."""

    field: str
    status: Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"]
    extracted: str | None
    expected: str
    method: str
    similarity: float | None = None
    note: str | None = None


class Comparator:
    """Compare extracted label fields against submitted application data."""

    def __init__(self, config: ComparisonConfig) -> None:
        self.config = config

    def compare_all(
        self,
        extracted: ExtractedFields,
        expected: ApplicationData,
    ) -> list[FieldComparison]:
        """Compare all declared application fields in stable field order."""
        results: list[FieldComparison] = []

        for field_name, strategy in FIELD_STRATEGIES.items():
            expected_value = getattr(expected, field_name)

            if expected_value is None:
                continue

            extracted_value = getattr(extracted, field_name)

            if field_name == "warning_statement":
                result = self.compare_warning_statement(extracted_value, expected_value)
            elif field_name == "brand_name":
                result = self.compare_brand_name(extracted_value, expected_value)
            elif field_name == "abv":
                result = self.compare_abv(extracted_value, expected_value)
            elif field_name == "net_contents":
                result = self.compare_net_contents(extracted_value, expected_value)
            elif strategy == "fuzzy_match":
                result = self._compare_fuzzy_field(
                    extracted_value,
                    expected_value,
                    field_name,
                )
            else:
                result = self.compare_text_field(
                    extracted_value,
                    expected_value,
                    field_name,
                )

            results.append(result)

        return results

    def compare_warning_statement(
        self,
        extracted: str | None,
        expected: str,
    ) -> FieldComparison:
        """Compare warning statement exactly after whitespace normalization.

        Case must remain significant. Do not lowercase this field.
        """
        field = "warning_statement"
        method: Literal["exact_match"] = "exact_match"

        if _is_missing(extracted):
            return FieldComparison(
                field=field,
                status="NOT_FOUND",
                extracted=extracted,
                expected=expected,
                method=method,
                note="Warning statement not found on label",
                confidence=None,
                similarity=None,
            )

        assert extracted is not None
        normalized_extracted = normalize_whitespace(extracted)
        normalized_expected = normalize_whitespace(expected)

        if normalized_extracted == normalized_expected:
            return FieldComparison(
                field=field,
                status="MATCH",
                extracted=extracted,
                expected=expected,
                method=method,
                similarity=1.0,
                note="Warning statement matches exactly",
                confidence=None,
            )

        note = "Warning statement does not match required text"
        if normalized_extracted.lower() == normalized_expected.lower():
            note = "Header not in required ALL CAPS format"
        elif normalized_expected.startswith(normalized_extracted):
            note = "Warning statement appears truncated"
        elif len(normalized_extracted) < len(normalized_expected) * 0.75:
            note = "Warning statement appears truncated"

        return FieldComparison(
            field=field,
            status="MISMATCH",
            extracted=extracted,
            expected=expected,
            method=method,
            note=note,
            confidence=None,
            similarity=None,
        )

    def compare_brand_name(
        self,
        extracted: str | None,
        expected: str,
    ) -> FieldComparison:
        """Compare brand names using fuzzy matching."""
        return self._compare_fuzzy_field(extracted, expected, "brand_name")

    def compare_abv(
        self,
        extracted: str | None,
        expected: str,
    ) -> FieldComparison:
        """Compare ABV using numeric extraction and configured tolerance."""
        field = "abv"
        method: Literal["numeric_match"] = "numeric_match"

        if _is_missing(extracted):
            return FieldComparison(
                field=field,
                status="NOT_FOUND",
                extracted=extracted,
                expected=expected,
                method=method,
                note="ABV not found on label",
                confidence=None,
                similarity=None,
            )

        assert extracted is not None
        extracted_num = extract_abv_numeric(extracted)
        expected_num = extract_abv_numeric(expected)

        if extracted_num is None or expected_num is None:
            return FieldComparison(
                field=field,
                status="MISMATCH",
                extracted=extracted,
                expected=expected,
                method=method,
                note="Could not extract a numeric ABV value",
                confidence=None,
                similarity=None,
            )

        diff = abs(extracted_num - expected_num)

        if diff == 0:
            status: Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"] = "MATCH"
            note = f"Extracted {extracted_num:g}% matches expected {expected_num:g}%"
        elif diff <= self.config.abv_tolerance:
            status = "WARNING"
            note = (
                f"Extracted {extracted_num:g}% vs expected {expected_num:g}% "
                f"within tolerance of {self.config.abv_tolerance:g}%"
            )
        else:
            status = "MISMATCH"
            note = (
                f"Extracted {extracted_num:g}% vs expected {expected_num:g}% "
                "exceeds allowed tolerance"
            )

        return FieldComparison(
            field=field,
            status=status,
            extracted=extracted,
            expected=expected,
            method=method,
            similarity=None,
            note=note,
            confidence=None,
        )

    def compare_net_contents(
        self,
        extracted: str | None,
        expected: str,
    ) -> FieldComparison:
        """Compare net contents by converting both values to milliliters."""
        field = "net_contents"
        method: Literal["numeric_match"] = "numeric_match"

        if _is_missing(extracted):
            return FieldComparison(
                field=field,
                status="NOT_FOUND",
                extracted=extracted,
                expected=expected,
                method=method,
                note="Net contents not found on label",
                confidence=None,
                similarity=None,
            )

        assert extracted is not None
        extracted_ml = extract_volume_ml(extracted)
        expected_ml = extract_volume_ml(expected)

        if extracted_ml is None or expected_ml is None:
            return FieldComparison(
                field=field,
                status="MISMATCH",
                extracted=extracted,
                expected=expected,
                method=method,
                note="Could not extract a numeric volume value",
                confidence=None,
                similarity=None,
            )

        if math.isclose(extracted_ml, expected_ml, rel_tol=0.0, abs_tol=0.001):
            status: Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"] = "MATCH"
            note = f"Extracted {extracted_ml:g} mL matches expected {expected_ml:g} mL"
        else:
            status = "MISMATCH"
            note = f"Extracted {extracted_ml:g} mL vs expected {expected_ml:g} mL"

        return FieldComparison(
            field=field,
            status=status,
            extracted=extracted,
            expected=expected,
            method=method,
            note=note,
            confidence=None,
            similarity=None,
        )

    def compare_text_field(
        self,
        extracted: str | None,
        expected: str,
        field_name: str,
    ) -> FieldComparison:
        """Compare normalized text fields such as class/type and origin."""
        method: Literal["normalized_match"] = "normalized_match"

        if _is_missing(extracted):
            return FieldComparison(
                field=field_name,
                status="NOT_FOUND",
                extracted=extracted,
                expected=expected,
                method=method,
                note=f"{field_name} not found on label",
                confidence=None,
                similarity=None,
            )

        assert extracted is not None
        normalized_extracted = normalize_string(extracted)
        normalized_expected = normalize_string(expected)

        if normalized_extracted == normalized_expected:
            return FieldComparison(
                field=field_name,
                status="MATCH",
                extracted=extracted,
                expected=expected,
                method=method,
                similarity=1.0,
                note=f"{field_name} matches after normalization",
                confidence=None,
            )

        ratio = _similarity_ratio(normalized_extracted, normalized_expected)
        status = self._status_from_similarity(ratio)

        return FieldComparison(
            field=field_name,
            status=status,
            extracted=extracted,
            expected=expected,
            method=method,
            similarity=round(ratio, 2),
            note=_similarity_note(field_name, status, ratio),
            confidence=None,
        )

    def _compare_fuzzy_field(
        self,
        extracted: str | None,
        expected: str,
        field_name: str,
    ) -> FieldComparison:
        """Compare a text field using fuzzy matching."""
        method: Literal["fuzzy_match"] = "fuzzy_match"

        if _is_missing(extracted):
            return FieldComparison(
                field=field_name,
                status="NOT_FOUND",
                extracted=extracted,
                expected=expected,
                method=method,
                note=f"{field_name} not found on label",
                confidence=None,
                similarity=None,
            )

        assert extracted is not None
        normalized_extracted = normalize_for_fuzzy_comparison(extracted)
        normalized_expected = normalize_for_fuzzy_comparison(expected)
        ratio = _similarity_ratio(normalized_extracted, normalized_expected)
        status = self._status_from_similarity(ratio)

        if normalized_extracted == normalized_expected:
            note = "Case or punctuation difference only"
        else:
            note = _similarity_note(field_name, status, ratio)

        return FieldComparison(
            field=field_name,
            status=status,
            extracted=extracted,
            expected=expected,
            method=method,
            similarity=round(ratio, 2),
            note=note,
            confidence=None,
        )

    def _status_from_similarity(
        self,
        ratio: float,
    ) -> Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"]:
        """Convert a similarity ratio to a comparison status."""
        if ratio >= self.config.match_threshold:
            return "MATCH"
        if ratio >= self.config.warning_threshold:
            return "WARNING"
        return "MISMATCH"


def derive_overall_status(
    field_results: list[FieldComparison],
) -> Literal["PASS", "REVIEW_NEEDED", "FAIL"]:
    """Derive the overall verification status from field-level results."""
    statuses = [field.status for field in field_results]
    if "MISMATCH" in statuses:
        return "FAIL"
    if "WARNING" in statuses or "NOT_FOUND" in statuses:
        return "REVIEW_NEEDED"
    return "PASS"


_DEFAULT_COMPARATOR = Comparator(ComparisonConfig())


def compare_warning_statement(
    extracted: str | None,
    expected: str,
) -> FieldComparison:
    """Compare warning statement using the default comparator."""
    return _DEFAULT_COMPARATOR.compare_warning_statement(extracted, expected)


def compare_brand_name(
    extracted: str | None,
    expected: str,
) -> FieldComparison:
    """Compare brand name using the default comparator."""
    return _DEFAULT_COMPARATOR.compare_brand_name(extracted, expected)


def compare_abv(extracted: str | None, expected: str) -> FieldComparison:
    """Compare ABV using the default comparator."""
    return _DEFAULT_COMPARATOR.compare_abv(extracted, expected)


def compare_net_contents(
    extracted: str | None,
    expected: str,
) -> FieldComparison:
    """Compare net contents using the default comparator."""
    return _DEFAULT_COMPARATOR.compare_net_contents(extracted, expected)


def compare_text_field(
    extracted: str | None,
    expected: str,
    field_name: str,
) -> FieldComparison:
    """Compare normalized text using the default comparator."""
    return _DEFAULT_COMPARATOR.compare_text_field(extracted, expected, field_name)


def _is_missing(value: str | None) -> bool:
    """Return True when an extracted value is absent or blank."""
    return value is None or not value.strip()


def _similarity_ratio(left: str, right: str) -> float:
    """Return fuzzy similarity as a 0.0-1.0 ratio."""
    return fuzz.ratio(left, right) / 100.0


def _similarity_note(
    field_name: str,
    status: str,
    ratio: float,
) -> str:
    """Build a human-readable similarity note."""
    percent = round(ratio * 100)
    if status == "MATCH":
        return f"{field_name} matches with {percent}% similarity"
    if status == "WARNING":
        return f"{field_name} has minor variation with {percent}% similarity"
    return f"{field_name} differs with {percent}% similarity"
