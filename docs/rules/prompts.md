# API Contracts & Schemas

## General Principles

- The FastAPI backend serves a REST API for the React frontend.
- All request/response types are Pydantic `BaseModel` subclasses. No raw dicts at API boundaries.
- All timestamps are ISO 8601 format.
- File uploads use `multipart/form-data`. Application data is JSON-encoded in a form field.
- Azure AI Vision and OpenAI are called via `httpx` async client — no SDKs.

## Internal Data Types

### Pydantic Models (`app/models/schemas.py`)

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from datetime import datetime


class ApplicationData(BaseModel):
    """Data from the COLA application that the label must match."""
    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(..., min_length=1, max_length=500, description="Brand name as submitted in application")
    class_type: str = Field(..., min_length=1, max_length=500, description="Class/type designation (e.g., Kentucky Straight Bourbon Whiskey)")
    abv: str = Field(..., min_length=1, max_length=50, description="Alcohol content as a number or percentage (e.g., '45' or '45%')")
    net_contents: str = Field(..., min_length=1, max_length=100, description="Net contents with unit (e.g., '750 mL')")
    warning_statement: str = Field(..., min_length=1, max_length=2000, description="Full government warning statement text")
    producer: str | None = Field(None, max_length=500, description="Name and address of bottler/producer")
    origin: str | None = Field(None, max_length=200, description="Country of origin (for imports)")


class ExtractedFields(BaseModel):
    """Fields extracted from the label image by the AI pipeline."""
    brand_name: str | None = None
    class_type: str | None = None
    abv: str | None = None
    net_contents: str | None = None
    warning_statement: str | None = None
    producer: str | None = None
    origin: str | None = None
    raw_ocr_text: str | None = Field(None, description="Full OCR text for debugging")


class FieldComparison(BaseModel):
    """Result of comparing one extracted field against the application data."""
    field: str = Field(..., description="Field name (brand_name, abv, etc.)")
    status: Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"]
    extracted: str | None = Field(None, description="Value extracted from label image")
    expected: str = Field(..., description="Value from application data")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="OCR confidence for this field")
    method: Literal["exact_match", "fuzzy_match", "numeric_match", "normalized_match"]
    similarity: float | None = Field(None, ge=0.0, le=1.0, description="Similarity score (for fuzzy matches)")
    note: str | None = Field(None, description="Human-readable explanation of the comparison result")


class ImageQuality(BaseModel):
    """Assessment of the uploaded image quality."""
    readable: bool = Field(..., description="Whether the image text was readable enough to extract")
    issues: list[str] = Field(default_factory=list, description="Detected issues (glare, angle, blur, low_resolution)")


class VerificationResult(BaseModel):
    """Complete verification result for a single label."""
    id: str = Field(..., description="Unique verification ID (ver_<uuid>)")
    status: Literal["PASS", "REVIEW_NEEDED", "FAIL"]
    processing_time_ms: int = Field(..., description="Total processing time in milliseconds")
    fields: list[FieldComparison] = Field(..., description="Per-field comparison results")
    image_quality: ImageQuality
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BatchStatus(BaseModel):
    """Status of a batch verification job."""
    batch_id: str
    status: Literal["processing", "complete", "failed"]
    total: int = Field(..., description="Total labels in batch")
    completed: int = Field(..., description="Labels processed so far")
    results: list[VerificationResult] | None = Field(None, description="Results when complete")


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: str | None = None
```

### Database Model (`app/models/database.py`)

```python
from sqlalchemy import Column, String, Integer, Float, DateTime, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()

class VerificationRecord(Base):
    __tablename__ = "verifications"

    id = Column(String, primary_key=True)           # ver_<uuid>
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, nullable=False)          # PASS, REVIEW_NEEDED, FAIL
    processing_time_ms = Column(Integer, nullable=False)
    application_data = Column(JSON, nullable=False)  # ApplicationData as dict
    field_results = Column(JSON, nullable=False)     # list[FieldComparison] as dicts
    image_quality = Column(JSON, nullable=False)     # ImageQuality as dict
    batch_id = Column(String, nullable=True)         # null for single verifications
```

### Comparison Engine Types (`app/services/comparator.py`)

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ComparisonConfig:
    """Configurable thresholds for field comparison."""
    match_threshold: float = 0.95        # >= this score = MATCH
    warning_threshold: float = 0.85      # >= this score = WARNING, below = MISMATCH
    abv_tolerance: float = 0.5           # numeric tolerance for ABV comparison
    normalize_case: bool = True          # lowercase before comparing
    normalize_whitespace: bool = True    # collapse whitespace before comparing
    normalize_punctuation: bool = True   # standardize quotes/apostrophes

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
```

## Azure AI Vision API

### Request

```
POST {endpoint}/computervision/imageanalysis:analyze?api-version=2024-02-01&features=read
Content-Type: application/octet-stream
Ocp-Apim-Subscription-Key: {key}
Body: <raw image bytes>
```

### Response (relevant fields)

```json
{
  "readResult": {
    "blocks": [
      {
        "lines": [
          {
            "text": "OLD TOM DISTILLERY",
            "boundingPolygon": [{"x": 100, "y": 50}, ...],
            "words": [
              {
                "text": "OLD",
                "boundingPolygon": [...],
                "confidence": 0.99
              }
            ]
          }
        ]
      }
    ]
  }
}
```

### Processing in `app/services/ocr.py`

```python
class OCRResult:
    text: str                    # all lines joined with newlines
    confidence: float            # average word confidence
    lines: list[OCRLine]         # individual lines with bounding boxes

class OCRLine:
    text: str
    confidence: float
    bounding_box: list[dict]     # polygon coordinates
```

Extract all `lines[].text` values, join with newlines. Calculate average confidence across all words. Return `OCRResult`.

## OpenAI GPT-4o API

### Request

```
POST https://api.openai.com/v1/chat/completions
Authorization: Bearer {api_key}
Content-Type: application/json
```

```json
{
  "model": "gpt-4o",
  "max_tokens": 1000,
  "temperature": 0.0,
  "response_format": { "type": "json_object" },
  "messages": [
    { "role": "system", "content": "<system prompt>" },
    { "role": "user", "content": "<OCR text>" }
  ]
}
```

### Response (relevant fields)

```json
{
  "choices": [
    {
      "message": {
        "content": "{\"brand_name\": \"OLD TOM DISTILLERY\", ...}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 450,
    "completion_tokens": 120,
    "total_tokens": 570
  }
}
```

### Processing in `app/services/parser.py`

Parse `choices[0].message.content` as JSON. Map to `ExtractedFields` Pydantic model. Handle missing fields gracefully (set to None). Log token usage for cost tracking.

## LLM Prompt Templates

### Field Extraction System Prompt

```
You are a label data extraction assistant for the TTB (Alcohol and Tobacco Tax and Trade Bureau).

You will receive raw OCR text extracted from an alcohol beverage label. Extract the following fields from the text and return them as a JSON object.

## Fields to Extract

- brand_name: The brand or trade name of the product (e.g., "OLD TOM DISTILLERY")
- class_type: The class and type designation (e.g., "Kentucky Straight Bourbon Whiskey")
- abv: The alcohol content exactly as printed, including any "Alc./Vol." or "Proof" notation (e.g., "45% Alc./Vol. (90 Proof)")
- net_contents: The net contents with unit (e.g., "750 mL")
- warning_statement: The complete government warning text, preserving exact capitalization and wording. Include the "GOVERNMENT WARNING:" header exactly as it appears.
- producer: The name and address of the bottler, producer, or importer
- origin: The country of origin (if stated)

## Rules

1. Extract text EXACTLY as it appears on the label. Do not correct spelling, capitalization, or formatting.
2. For the warning statement, preserve the EXACT capitalization of "GOVERNMENT WARNING:" — this is a compliance requirement.
3. If a field is not present or not readable in the OCR text, set it to null.
4. Do not infer or fabricate information that is not in the OCR text.
5. Return ONLY the JSON object, no additional text or explanation.

## Output Format

{
  "brand_name": "string or null",
  "class_type": "string or null",
  "abv": "string or null",
  "net_contents": "string or null",
  "warning_statement": "string or null",
  "producer": "string or null",
  "origin": "string or null"
}
```

### Field Extraction User Message

```
Extract the label fields from the following OCR text:

---
{ocr_text}
---
```

### Prompt Design Rationale

- **Temperature 0.0** — We want deterministic extraction, not creative interpretation.
- **JSON mode** — `response_format: json_object` ensures parseable output without markdown fences.
- **"Extract EXACTLY as it appears"** — Critical for warning statement compliance. The LLM must not "fix" the capitalization of "GOVERNMENT WARNING:" to "Government Warning:" — that correction would mask a label violation.
- **Null for missing fields** — Better to return null than to hallucinate a field value. The comparison engine handles null as NOT_FOUND status.
- **No application data in the prompt** — The LLM never sees the expected values. It extracts purely from OCR text. Comparison happens in deterministic Python code. This prevents the LLM from anchoring to expected values and "seeing" text that isn't there.

## REST API Endpoints

### POST `/api/verify`

Single label verification.

**Request:** `multipart/form-data`
- `file`: Image file (JPEG, PNG, or PDF, max 10MB)
- `application_data`: JSON string matching `ApplicationData` schema

**Response 200:** `VerificationResult`

**Response 400:** `ErrorResponse` — invalid file type or size

**Response 422:** Pydantic validation error — malformed application_data

**Response 502:** `ErrorResponse` — Azure or OpenAI API failure

### POST `/api/batch`

Submit batch verification job.

**Request:** `multipart/form-data`
- `files`: Multiple image files (max 50)
- `application_data`: JSON array of `ApplicationData` objects (one per file, matched by index)

**Response 202:** `{ "batch_id": "bat_<uuid>", "status": "processing", "total": 5, "completed": 0 }`

**Response 400:** `ErrorResponse` — file count mismatch, exceeds max batch size

### GET `/api/batch/{batch_id}`

Poll batch status.

**Response 200:** `BatchStatus` (status may be "processing" or "complete")

**Response 404:** `ErrorResponse` — batch not found

### GET `/api/history`

Query past verification results.

**Query params:**
- `limit`: int (default 20, max 100)
- `offset`: int (default 0)
- `status`: optional filter ("PASS", "REVIEW_NEEDED", "FAIL")

**Response 200:**
```json
{
  "total": 142,
  "limit": 20,
  "offset": 0,
  "results": [ ...VerificationResult... ]
}
```

## Constants (`app/utils/constants.py`)

```python
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
```
