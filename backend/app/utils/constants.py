"""Shared constants for label verification."""

# Standard government warning statement text
GOVERNMENT_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, "
    "women should not drink alcoholic beverages during pregnancy "
    "because of the risk of birth defects. (2) Consumption of "
    "alcoholic beverages impairs your ability to drive a car or "
    "operate machinery, and may cause health problems."
)


# GPT field extraction prompts
FIELD_EXTRACTION_SYSTEM_PROMPT = (
    "You are a label data extraction assistant for the TTB "
    "(Alcohol and Tobacco Tax and Trade Bureau).\n\n"
    "You will receive raw OCR text extracted from an alcohol beverage label. "
    "Extract the following fields from the text and return them as a JSON "
    "object.\n\n"
    "## Fields to Extract\n\n"
    "- brand_name: The brand or trade name of the product "
    '(e.g., "OLD TOM DISTILLERY")\n'
    "- class_type: The class and type designation "
    '(e.g., "Kentucky Straight Bourbon Whiskey")\n'
    "- abv: The alcohol content exactly as printed, including any "
    '"Alc./Vol." or "Proof" notation '
    '(e.g., "45% Alc./Vol. (90 Proof)")\n'
    '- net_contents: The net contents with unit (e.g., "750 mL")\n'
    "- warning_statement: The complete government warning text, preserving "
    'exact capitalization and wording. Include the "GOVERNMENT WARNING:" '
    "header exactly as it appears.\n"
    "- producer: The name and address of the bottler, producer, or importer\n"
    "- origin: The country of origin (if stated)\n\n"
    "## Rules\n\n"
    "1. Extract text EXACTLY as it appears on the label. Do not correct "
    "spelling, capitalization, or formatting.\n"
    "2. For the warning statement, preserve the EXACT capitalization of "
    '"GOVERNMENT WARNING:" — this is a compliance requirement.\n'
    "3. If a field is not present or not readable in the OCR text, set it "
    "to null.\n"
    "4. Do not infer or fabricate information that is not in the OCR text.\n"
    "5. Return ONLY the JSON object, no additional text or explanation.\n\n"
    "## Output Format\n\n"
    "{\n"
    '  "brand_name": "string or null",\n'
    '  "class_type": "string or null",\n'
    '  "abv": "string or null",\n'
    '  "net_contents": "string or null",\n'
    '  "warning_statement": "string or null",\n'
    '  "producer": "string or null",\n'
    '  "origin": "string or null"\n'
    "}\n"
)

FIELD_EXTRACTION_USER_TEMPLATE = (
    "Extract the label fields from the following OCR text:\n\n---\n{ocr_text}\n---"
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
