"""Shared constants for label verification."""

# Standard government warning statement text
GOVERNMENT_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
    "women should not drink alcoholic beverages during pregnancy "
    "because of the risk of birth defects. (2) Consumption of "
    "alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)

# Supported image MIME types
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "application/pdf"}

# File size limits
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_BATCH_SIZE = 50

# Comparison thresholds (overridable via env vars)
DEFAULT_MATCH_THRESHOLD = 0.95
DEFAULT_WARNING_THRESHOLD = 0.85
DEFAULT_ABV_TOLERANCE = 0.5

# Fields and their comparison strategies
FIELD_STRATEGIES = {
    "brand_name": "fuzzy_match",
    "class_type": "normalized_match",
    "abv": "numeric_match",
    "net_contents": "numeric_match",
    "warning_statement": "exact_match",
    "producer": "fuzzy_match",
    "origin": "normalized_match",
}
