"""Text normalization and numeric extraction helpers for label comparison."""

import re


def normalize_whitespace(text: str) -> str:
    """Collapse all runs of whitespace to a single space and strip edges."""
    return " ".join(text.split())


def normalize_unicode_punctuation(text: str) -> str:
    """Replace common Unicode punctuation with ASCII equivalents."""
    replacements = {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    return text


def normalize_for_fuzzy_comparison(text: str) -> str:
    """Lowercase, normalize whitespace, and normalize Unicode punctuation."""
    text = text.lower()
    text = normalize_whitespace(text)
    text = normalize_unicode_punctuation(text)
    return text


def extract_abv_numeric(text: str) -> float | None:
    """Extract ABV percentage from percent, proof, or bare-number formats."""
    pct_match = re.search(r"(\d+\.?\d*)\s*%", text)
    if pct_match:
        return float(pct_match.group(1))

    proof_match = re.search(r"(\d+\.?\d*)\s*[Pp]roof", text)
    if proof_match:
        return float(proof_match.group(1)) / 2.0

    bare_match = re.search(r"(\d+\.?\d*)", text)
    if bare_match:
        return float(bare_match.group(1))

    return None


def extract_volume_ml(text: str) -> float | None:
    """Extract volume from mL, L, or fluid-ounce formats and return milliliters."""
    ml_match = re.search(r"(\d+\.?\d*)\s*[Mm][Ll]", text)
    if ml_match:
        return float(ml_match.group(1))

    l_match = re.search(r"(\d+\.?\d*)\s*[Ll](?!\w)", text)
    if l_match:
        return float(l_match.group(1)) * 1000.0

    oz_match = re.search(r"(\d+\.?\d*)\s*(?:fl\.?\s*oz|oz)", text, re.IGNORECASE)
    if oz_match:
        return float(oz_match.group(1)) * 29.5735

    return None


def extract_numeric_value(text: str) -> float | None:
    """Extract a numeric value from ABV/proof, volume, or bare-number text."""
    has_abv_marker = "%" in text or re.search(r"\bproof\b", text, re.IGNORECASE)
    if has_abv_marker:
        return extract_abv_numeric(text)

    volume_value = extract_volume_ml(text)
    if volume_value is not None:
        return volume_value

    bare_match = re.search(r"(\d+\.?\d*)", text)
    if bare_match:
        return float(bare_match.group(1))

    return None


def strip_punctuation(text: str) -> str:
    """Remove punctuation for normalized string comparison."""
    return re.sub(r"[^\w\s]", "", text)


def normalize_string(text: str) -> str:
    """Normalize text for strict normalized matching.

    This lowercases text, normalizes whitespace and Unicode punctuation, strips
    punctuation, and collapses whitespace again.
    """
    text = normalize_for_fuzzy_comparison(text)
    text = strip_punctuation(text)
    return normalize_whitespace(text)
