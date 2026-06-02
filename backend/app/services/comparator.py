"""Comparison engine types.

The deterministic comparison engine is implemented in Phase 4. This module owns
the comparison configuration and result dataclasses so other modules can import
the canonical types before the full engine exists.
"""

from dataclasses import dataclass
from typing import Literal


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
