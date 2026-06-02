# Technical Specification
## TTB Label Verification Tool

**Version:** 1.0 (Prototype)
**Date:** June 2026

---

## 1. System Overview

The TTB Label Verification Tool is a client-server web application with a three-stage AI pipeline at its core. The frontend collects label images and application data from compliance agents. The backend orchestrates OCR extraction, LLM-based field structuring, and deterministic field comparison, then returns per-field verdicts to the frontend.

```
┌──────────┐     REST/JSON      ┌──────────────────────────────────────┐
│  React   │◄──────────────────►│           FastAPI Backend            │
│ Frontend │                    │                                      │
└──────────┘                    │  ┌────────┐ ┌────────┐ ┌──────────┐ │
                                │  │  OCR   │→│ Parser │→│Comparator│ │
                                │  │Service │ │Service │ │ Engine   │ │
                                │  └───┬────┘ └───┬────┘ └──────────┘ │
                                │      │          │                    │
                                │      ▼          ▼                    │
                                │  Azure AI    OpenAI     ┌────────┐  │
                                │  Vision      GPT-4o     │ SQLite │  │
                                │                         └────────┘  │
                                └──────────────────────────────────────┘
```

### Design Principles

1. **Deterministic core, AI at the edges.** The comparison engine is pure Python with zero external calls. AI services handle extraction only. This makes the business logic testable, auditable, and explainable.

2. **Assist, never override.** The tool produces verdicts and evidence. The agent makes the final decision. No auto-approve, no auto-reject.

3. **Fail transparent, not silent.** When the AI is uncertain, the system says so (WARNING status with confidence score). When it fails, the error message tells the agent what to do next.

4. **Speed is a feature.** Every architectural decision accounts for the 5-second time budget. Two fast API calls (OCR + GPT) are acceptable. Three are not.

---

## 2. Backend Architecture

### 2.1 Application Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, middleware, lifespan
│   ├── config.py                # Environment variable loading and validation
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── verify.py            # POST /api/verify
│   │   ├── batch.py             # POST /api/batch, GET /api/batch/{id}
│   │   └── history.py           # GET /api/history
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ocr.py               # Azure AI Vision client
│   │   ├── parser.py            # GPT-4o field extraction
│   │   ├── comparator.py        # Comparison engine (PURE PYTHON — NO I/O)
│   │   └── pipeline.py          # Orchestrator: OCR → Parser → Comparator
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── database.py          # SQLAlchemy models, engine, session
│   └── utils/
│       ├── __init__.py
│       ├── normalization.py     # Text normalization functions
│       └── constants.py         # Warning text, thresholds, field strategies
```

### 2.2 Application Lifecycle (`app/main.py`)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: validate env vars, init DB, warm up HTTP clients
    config = load_and_validate_config()
    init_database(config.database_url)
    app.state.ocr_service = OCRService(config.azure_endpoint, config.azure_key)
    app.state.parser_service = GPTParser(config.openai_key)
    app.state.comparator = Comparator(config.comparison_config)
    yield
    # Shutdown: close HTTP clients
    await app.state.ocr_service.close()
    await app.state.parser_service.close()

app = FastAPI(title="TTB Label Verification", lifespan=lifespan)
app.add_middleware(CORSMiddleware, ...)
app.include_router(verify_router, prefix="/api")
app.include_router(batch_router, prefix="/api")
app.include_router(history_router, prefix="/api")
```

### 2.3 Configuration (`app/config.py`)

All configuration loaded from environment variables at startup. Fail fast if required values are missing.

```python
@dataclass(frozen=True)
class AppConfig:
    # Required — startup fails without these
    azure_vision_endpoint: str
    azure_vision_key: str
    openai_api_key: str

    # Optional with defaults
    database_url: str = "sqlite:///./verification.db"
    log_level: str = "info"
    max_batch_size: int = 50
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
    ocr_timeout_seconds: float = 30.0
    gpt_timeout_seconds: float = 60.0
    ocr_concurrency_limit: int = 5
    gpt_concurrency_limit: int = 3

    # Comparison thresholds
    comparison_config: ComparisonConfig  # see comparator types
```

---

## 3. Pipeline Detail

### 3.1 Stage 1 — OCR Extraction (`app/services/ocr.py`)

**Input:** Raw image bytes (JPEG, PNG, or PDF)
**Output:** `OCRResult` (full text, per-line text with confidence, bounding boxes)
**External dependency:** Azure AI Vision Read API
**Target latency:** < 2000ms

```python
class OCRService:
    async def extract_text(self, image_bytes: bytes, content_type: str) -> OCRResult:
        """Send image to Azure AI Vision and return structured OCR result."""

class OCRResult:
    text: str                           # All lines joined with \n
    lines: list[OCRLine]                # Per-line detail
    average_confidence: float           # Mean word confidence (0.0–1.0)
    image_quality_issues: list[str]     # Detected issues: "low_confidence", etc.

class OCRLine:
    text: str
    confidence: float
    bounding_polygon: list[Point]
```

**Azure API call:**

```
POST {endpoint}/computervision/imageanalysis:analyze
  ?api-version=2024-02-01
  &features=read
Content-Type: application/octet-stream
Ocp-Apim-Subscription-Key: {key}
Body: <image bytes>
```

**Processing logic:**
1. Send raw image bytes to Azure AI Vision.
2. Parse response: iterate `readResult.blocks[].lines[]`.
3. For each line, extract `.text`, `.words[].confidence`, `.boundingPolygon`.
4. Join all line texts with newlines to produce `OCRResult.text`.
5. Calculate `average_confidence` as mean of all word confidences.
6. If `average_confidence < 0.70`, add `"low_confidence"` to `image_quality_issues`.
7. Return `OCRResult`.

**Error handling:**
- HTTP 4xx from Azure → raise `OCRExtractionError` with status code context.
- HTTP 5xx or timeout → raise `OCRExtractionError("Azure AI Vision unavailable")`.
- Empty response (no text extracted) → return `OCRResult` with empty text and `["no_text_detected"]` in issues.

### 3.2 Stage 2 — Field Structuring (`app/services/parser.py`)

**Input:** `OCRResult.text` (raw OCR text string)
**Output:** `ExtractedFields` (Pydantic model with labeled field values)
**External dependency:** OpenAI GPT-4o API
**Target latency:** < 2000ms

```python
class GPTParser:
    async def extract_fields(self, ocr_text: str) -> ExtractedFields:
        """Send OCR text to GPT-4o and return structured field extraction."""
```

**OpenAI API call:**

```json
{
  "model": "gpt-4o",
  "max_tokens": 1000,
  "temperature": 0.0,
  "response_format": { "type": "json_object" },
  "messages": [
    { "role": "system", "content": "< extraction system prompt >" },
    { "role": "user", "content": "Extract the label fields from the following OCR text:\n\n---\n{ocr_text}\n---" }
  ]
}
```

**System prompt:** See `docs/prompts.md` for the full template. Key rules:
- Extract text EXACTLY as it appears (do not correct capitalization or spelling).
- Set field to `null` if not present or not readable.
- Do not infer or fabricate information.
- Return only the JSON object.

**Processing logic:**
1. Construct messages with system prompt and OCR text.
2. Call OpenAI API with `temperature=0.0` and `response_format=json_object`.
3. Parse `choices[0].message.content` as JSON.
4. Map to `ExtractedFields` Pydantic model.
5. Log token usage (`usage.total_tokens`) for cost tracking.
6. Return `ExtractedFields`.

**Error handling:**
- JSON parse failure → raise `ParserError("GPT returned non-JSON response")`.
- Missing required structure in JSON → map missing fields to `None`, do not raise.
- HTTP 429 (rate limit) → raise `ParserError` with retry-after context.
- HTTP 4xx/5xx → raise `ParserError` with status code.

**Critical design constraint:** The application data (expected values) is NEVER sent to GPT. The LLM extracts from OCR text only. Comparison happens in Stage 3. This prevents anchoring bias where the LLM "sees" expected text that isn't actually on the label.

### 3.3 Stage 3 — Comparison Engine (`app/services/comparator.py`)

**Input:** `ExtractedFields` + `ApplicationData`
**Output:** `list[FieldComparison]`
**External dependencies:** NONE. Pure Python.
**Target latency:** < 50ms

```python
class Comparator:
    def __init__(self, config: ComparisonConfig):
        self.config = config

    def compare_all(
        self, extracted: ExtractedFields, expected: ApplicationData
    ) -> list[FieldComparison]:
        """Compare all fields and return per-field verdicts."""

    def compare_warning_statement(self, extracted: str | None, expected: str) -> FieldComparison: ...
    def compare_brand_name(self, extracted: str | None, expected: str) -> FieldComparison: ...
    def compare_abv(self, extracted: str | None, expected: str) -> FieldComparison: ...
    def compare_net_contents(self, extracted: str | None, expected: str) -> FieldComparison: ...
    def compare_text_field(self, extracted: str | None, expected: str, field_name: str) -> FieldComparison: ...
```

#### 3.3.1 Comparison Strategies

**Exact Match** (warning_statement)

```
normalize_whitespace(extracted) == normalize_whitespace(expected)
```

Warning statement must match word-for-word after collapsing whitespace. Capitalization is NOT normalized — "GOVERNMENT WARNING:" vs "Government Warning:" is a real mismatch that must be caught.

Steps:
1. If `extracted` is `None` or empty → `NOT_FOUND`.
2. Normalize whitespace on both values (collapse runs of spaces/tabs/newlines to single space, strip leading/trailing).
3. Compare strings. Exact match → `MATCH`. Any difference → `MISMATCH`.
4. Generate note explaining the specific difference (e.g., "Header not in required ALL CAPS format", "Text truncated after word 15").

**Fuzzy Match** (brand_name, producer)

```
ratio = fuzz.ratio(normalize(extracted), normalize(expected)) / 100.0
```

Steps:
1. If `extracted` is `None` or empty → `NOT_FOUND`.
2. Normalize both values: lowercase, collapse whitespace, normalize unicode punctuation (smart quotes → ASCII).
3. Calculate Levenshtein ratio using `fuzzywuzzy.fuzz.ratio`.
4. Apply thresholds:
   - `ratio >= config.match_threshold` (default 0.95) → `MATCH`
   - `ratio >= config.warning_threshold` (default 0.85) → `WARNING`
   - `ratio < config.warning_threshold` → `MISMATCH`
5. Store similarity score in result.
6. Generate note describing the difference (e.g., "Case difference only", "Minor character substitution at position 12").

**Numeric Match** (abv, net_contents)

```
extracted_num = extract_numeric(extracted)
expected_num = extract_numeric(expected)
abs(extracted_num - expected_num) <= tolerance
```

Steps:
1. If `extracted` is `None` or empty → `NOT_FOUND`.
2. Extract numeric value from both strings using regex: `r"(\d+\.?\d*)"`.
3. For ABV: if extracted contains "Proof" but not "%", divide by 2 to convert to ABV.
4. For net_contents: normalize units (L → mL × 1000, fl oz → mL × 29.5735).
5. Compare numeric values:
   - Exact match → `MATCH`
   - Within tolerance (ABV: ±0.5, net_contents: ±0) → `WARNING`
   - Outside tolerance → `MISMATCH`
6. Store both original strings and extracted numerics in result.

**Normalized String Match** (class_type, origin)

```
normalize(extracted) == normalize(expected)
```

Steps:
1. If `extracted` is `None` or empty → `NOT_FOUND`.
2. Normalize both: lowercase, collapse whitespace, strip punctuation.
3. Exact match after normalization → `MATCH`.
4. If not exact, fall back to fuzzy match with same thresholds as brand_name.

#### 3.3.2 Overall Verdict Derivation

```python
def derive_overall_status(field_results: list[FieldComparison]) -> str:
    statuses = [f.status for f in field_results]
    if "MISMATCH" in statuses:
        return "FAIL"
    if "WARNING" in statuses or "NOT_FOUND" in statuses:
        return "REVIEW_NEEDED"
    return "PASS"
```

### 3.4 Pipeline Orchestrator (`app/services/pipeline.py`)

Coordinates the three stages and handles timing.

```python
class VerificationPipeline:
    def __init__(self, ocr: OCRService, parser: GPTParser, comparator: Comparator):
        self.ocr = ocr
        self.parser = parser
        self.comparator = comparator

    async def verify(
        self, image_bytes: bytes, content_type: str, application_data: ApplicationData
    ) -> VerificationResult:
        start = time.monotonic()

        # Stage 1: OCR
        ocr_result = await self.ocr.extract_text(image_bytes, content_type)

        # Stage 2: Parse
        extracted = await self.parser.extract_fields(ocr_result.text)

        # Stage 3: Compare (sync — pure Python, < 50ms)
        field_results = self.comparator.compare_all(extracted, application_data)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        return VerificationResult(
            id=f"ver_{uuid4().hex[:12]}",
            status=derive_overall_status(field_results),
            processing_time_ms=elapsed_ms,
            fields=field_results,
            image_quality=ImageQuality(
                readable=bool(ocr_result.text.strip()),
                issues=ocr_result.image_quality_issues,
            ),
        )
```

---

## 4. API Endpoints

### 4.1 POST `/api/verify`

Single label verification.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | Label image (JPEG, PNG, PDF). Max 10MB. |
| `application_data` | String (JSON) | Yes | JSON-encoded `ApplicationData` object. |

**Validation (before processing):**
1. Verify `file` content type is in `{image/jpeg, image/png, application/pdf}`.
2. Verify `file` size ≤ 10MB.
3. Validate magic bytes match declared content type.
4. Parse `application_data` as `ApplicationData` Pydantic model.
5. Reject if any validation fails → 400 or 422.

**Response 200:**
```json
{
  "id": "ver_a1b2c3d4e5f6",
  "status": "REVIEW_NEEDED",
  "processing_time_ms": 3420,
  "fields": [
    {
      "field": "brand_name",
      "status": "MATCH",
      "extracted": "OLD TOM DISTILLERY",
      "expected": "OLD TOM DISTILLERY",
      "confidence": 0.98,
      "method": "fuzzy_match",
      "similarity": 1.0,
      "note": null
    }
  ],
  "image_quality": {
    "readable": true,
    "issues": []
  },
  "timestamp": "2026-06-01T14:30:00Z"
}
```

**Handler pseudocode:**

```python
@router.post("/verify", response_model=VerificationResult)
async def verify_label(
    file: UploadFile,
    application_data: str = Form(...),
    pipeline: VerificationPipeline = Depends(get_pipeline),
    db: Session = Depends(get_db),
):
    validate_upload(file)
    app_data = ApplicationData.model_validate_json(application_data)
    image_bytes = await file.read()
    result = await pipeline.verify(image_bytes, file.content_type, app_data)
    save_verification(db, result, app_data)
    return result
```

### 4.2 POST `/api/batch`

Submit batch verification job. Returns immediately with a batch ID. Processing happens asynchronously.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | File[] | Yes | Up to 50 label images. |
| `application_data` | String (JSON) | Yes | JSON array of `ApplicationData` objects, one per file (matched by index). |

**Validation:**
1. File count ≤ `MAX_BATCH_SIZE` (default 50).
2. File count matches `application_data` array length.
3. Each file passes individual validation (type, size).
4. Each `ApplicationData` entry validates.

**Response 202:**
```json
{
  "batch_id": "bat_x9y8z7w6",
  "status": "processing",
  "total": 12,
  "completed": 0,
  "results": null
}
```

**Background processing:**

```python
async def process_batch(batch_id: str, items: list[BatchItem]):
    semaphore = asyncio.Semaphore(OCR_CONCURRENCY_LIMIT)
    results = []

    async def process_one(item: BatchItem):
        async with semaphore:
            result = await pipeline.verify(item.image_bytes, item.content_type, item.app_data)
            results.append(result)
            update_batch_progress(batch_id, len(results))

    await asyncio.gather(*[process_one(item) for item in items])
    finalize_batch(batch_id, results)
```

### 4.3 GET `/api/batch/{batch_id}`

Poll batch status.

**Response 200 (processing):**
```json
{
  "batch_id": "bat_x9y8z7w6",
  "status": "processing",
  "total": 12,
  "completed": 7,
  "results": null
}
```

**Response 200 (complete):**
```json
{
  "batch_id": "bat_x9y8z7w6",
  "status": "complete",
  "total": 12,
  "completed": 12,
  "results": [ ...VerificationResult[] ]
}
```

**Response 404:** Batch not found.

### 4.4 GET `/api/history`

Query past verification results.

**Query parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 20 | Results per page (max 100) |
| `offset` | int | 0 | Pagination offset |
| `status` | string | null | Filter: "PASS", "REVIEW_NEEDED", "FAIL" |

**Response 200:**
```json
{
  "total": 142,
  "limit": 20,
  "offset": 0,
  "results": [ ...VerificationResult[] ]
}
```

---

## 5. Frontend Architecture

### 5.1 Component Tree

```
App
├── Header (logo, nav: Single | Batch | History)
├── SingleVerification (default view)
│   ├── UploadZone
│   │   └── ImagePreview
│   ├── ApplicationForm
│   │   └── FormField (×7)
│   ├── VerifyButton
│   └── ResultsPanel
│       ├── OverallStatus
│       └── FieldResult (×n)
│           ├── StatusBadge
│           ├── ExtractedValue
│           ├── ExpectedValue
│           └── SimilarityScore
├── BatchVerification
│   ├── BatchUpload
│   │   └── FileList
│   ├── BatchDataInput
│   ├── BatchProgress
│   └── BatchResults
│       └── BatchRow (×n, expandable → ResultsPanel)
└── History
    ├── StatusFilter
    └── HistoryTable
        └── HistoryRow (×n, expandable → ResultsPanel)
```

### 5.2 Key Component Specifications

**UploadZone**
- Drag-and-drop area with dashed border, icon, and "Drop label image here" text.
- Fallback: "or click to browse" button inside the zone.
- On drop/select: validate file type client-side, show image preview, store in state.
- Accept: `.jpg`, `.jpeg`, `.png`, `.pdf`.
- Visual feedback on dragover (border color change).
- Minimum click target: 200×150px.

**ApplicationForm**
- Seven labeled fields in a vertical form layout.
- Required fields (brand_name, class_type, abv, net_contents, warning_statement) marked with asterisk.
- Optional fields (producer, origin) clearly labeled as optional.
- Warning statement field is a `<textarea>` with 4-row height.
- Form validation on submit — highlight missing required fields.
- Pre-fill with sample data button (for demo/testing).

**ResultsPanel**
- Appears below the form after verification completes.
- Overall status banner at top: green (PASS), yellow (REVIEW_NEEDED), red (FAIL).
- Per-field rows stacked vertically. Each row shows: field name, status badge, extracted value, expected value, similarity score (if applicable), explanatory note.
- Fields with MISMATCH are visually prominent (red border/background).
- Fields with WARNING use yellow. MATCH uses green. NOT_FOUND uses gray.
- Processing time displayed at bottom: "Verified in 3.4 seconds".

**StatusBadge**
- Colored pill/badge with icon AND text.
- ✅ MATCH (green background, checkmark icon)
- ❌ MISMATCH (red background, X icon)
- ⚠️ WARNING (yellow background, alert icon)
- ➖ NOT_FOUND (gray background, dash icon)
- Never rely on color alone (accessibility).

### 5.3 State Management

```
App State:
├── view: "single" | "batch" | "history"
├── single:
│   ├── imageFile: File | null
│   ├── imagePreview: string | null (data URL)
│   ├── applicationData: ApplicationData | null
│   ├── isVerifying: boolean
│   ├── result: VerificationResult | null
│   └── error: string | null
├── batch:
│   ├── files: File[]
│   ├── applicationDataList: ApplicationData[]
│   ├── batchId: string | null
│   ├── isProcessing: boolean
│   ├── progress: { total: number, completed: number }
│   ├── results: VerificationResult[] | null
│   └── error: string | null
└── history:
    ├── results: VerificationResult[]
    ├── total: number
    ├── statusFilter: string | null
    ├── isLoading: boolean
    └── page: number
```

### 5.4 API Integration

```javascript
// Single verification
async function verifyLabel(imageFile, applicationData) {
  const formData = new FormData();
  formData.append("file", imageFile);
  formData.append("application_data", JSON.stringify(applicationData));

  const response = await fetch(`${API_URL}/api/verify`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || error.error || "Verification failed");
  }

  return response.json();
}

// Batch polling
async function pollBatchStatus(batchId, onProgress) {
  while (true) {
    const response = await fetch(`${API_URL}/api/batch/${batchId}`);
    const status = await response.json();
    onProgress(status);

    if (status.status === "complete" || status.status === "failed") {
      return status;
    }

    await new Promise((r) => setTimeout(r, 1000)); // Poll every 1s
  }
}
```

---

## 6. Database Schema

Single table for the prototype. No relations, no migrations — SQLite with SQLAlchemy.

```sql
CREATE TABLE verifications (
    id              TEXT PRIMARY KEY,           -- "ver_<uuid12>"
    timestamp       DATETIME NOT NULL,
    status          TEXT NOT NULL,              -- "PASS" | "REVIEW_NEEDED" | "FAIL"
    processing_time_ms INTEGER NOT NULL,
    application_data TEXT NOT NULL,             -- JSON blob
    field_results   TEXT NOT NULL,              -- JSON blob (list of FieldComparison)
    image_quality   TEXT NOT NULL,              -- JSON blob
    batch_id        TEXT                        -- NULL for single verifications
);

CREATE INDEX idx_verifications_timestamp ON verifications(timestamp DESC);
CREATE INDEX idx_verifications_status ON verifications(status);
CREATE INDEX idx_verifications_batch_id ON verifications(batch_id);
```

**Why JSON blobs instead of normalized tables:** This is a prototype. The audit trail needs to record exactly what happened. Querying individual field results is not a prototype requirement. If it becomes one, the JSON can be queried with SQLite's `json_extract()` function, or the schema can be normalized in a production migration.

---

## 7. Text Normalization (`app/utils/normalization.py`)

All normalization functions are pure, stateless, and independently testable.

```python
def normalize_whitespace(text: str) -> str:
    """Collapse all runs of whitespace to single space, strip edges."""
    return " ".join(text.split())

def normalize_for_fuzzy_comparison(text: str) -> str:
    """Lowercase, normalize whitespace, normalize unicode punctuation."""
    text = text.lower()
    text = normalize_whitespace(text)
    text = normalize_unicode_punctuation(text)
    return text

def normalize_unicode_punctuation(text: str) -> str:
    """Replace smart quotes, em dashes, etc. with ASCII equivalents."""
    replacements = {
        "\u2018": "'", "\u2019": "'",   # smart single quotes
        "\u201c": '"', "\u201d": '"',   # smart double quotes
        "\u2013": "-", "\u2014": "-",   # en dash, em dash
        "\u2026": "...",                 # ellipsis
    }
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    return text

def extract_abv_numeric(text: str) -> float | None:
    """Extract ABV percentage from various formats."""
    # Try percentage first: "45% Alc./Vol."
    pct_match = re.search(r"(\d+\.?\d*)\s*%", text)
    if pct_match:
        return float(pct_match.group(1))

    # Try proof: "90 Proof" → 45.0
    proof_match = re.search(r"(\d+\.?\d*)\s*[Pp]roof", text)
    if proof_match:
        return float(proof_match.group(1)) / 2.0

    # Try bare number
    bare_match = re.search(r"(\d+\.?\d*)", text)
    if bare_match:
        return float(bare_match.group(1))

    return None

def extract_volume_ml(text: str) -> float | None:
    """Extract volume in mL from various formats."""
    # "750 mL", "750ml", "1 L", "1.75L"
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
```

---

## 8. Error Handling Strategy

### External Service Errors

| Service | Error | User-Facing Message | HTTP Status |
|---------|-------|---------------------|-------------|
| Azure Vision | 401 Unauthorized | "Image processing service configuration error. Contact support." | 502 |
| Azure Vision | 429 Rate Limited | "Image processing service is busy. Please try again in a moment." | 503 |
| Azure Vision | 500/503 | "Image processing service is temporarily unavailable." | 502 |
| Azure Vision | Timeout | "Image processing timed out. Try a smaller or clearer image." | 504 |
| OpenAI | 401 Unauthorized | "Text analysis service configuration error. Contact support." | 502 |
| OpenAI | 429 Rate Limited | "Text analysis service is busy. Please try again in a moment." | 503 |
| OpenAI | Non-JSON response | "Text analysis produced unexpected results. Please try again." | 502 |

### Validation Errors

| Error | User-Facing Message | HTTP Status |
|-------|---------------------|-------------|
| Unsupported file type | "Please upload a JPEG, PNG, or PDF image." | 400 |
| File too large | "Image must be under 10MB." | 400 |
| Missing required field | Pydantic field-level error details | 422 |
| Batch size exceeded | "Maximum 50 labels per batch." | 400 |
| File count mismatch | "Number of images (N) doesn't match number of application records (M)." | 400 |

### Internal Errors

All unexpected exceptions are caught by a global handler that returns `{"error": "An unexpected error occurred", "detail": "Please try again or contact support"}` with status 500. Full exception details are logged server-side only.

---

## 9. Deployment

### 9.1 Docker (Prototype)

Multi-stage build: frontend build → Python runtime with static assets.

```dockerfile
# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production=false
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
RUN useradd --create-home appuser
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/frontend/dist ./static

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.2 Azure App Service

```bash
# Build and push to Azure Container Registry
az acr build --registry <registry> --image ttb-verify:latest .

# Create App Service
az webapp create \
  --name ttb-label-verify \
  --resource-group ttb-rg \
  --plan ttb-plan \
  --deployment-container-image-name <registry>.azurecr.io/ttb-verify:latest

# Set environment variables
az webapp config appsettings set \
  --name ttb-label-verify \
  --settings \
    AZURE_VISION_ENDPOINT=https://... \
    AZURE_VISION_KEY=... \
    OPENAI_API_KEY=... \
    DATABASE_URL=sqlite:///./verification.db
```

---

## 10. Testing Strategy Summary

| Layer | What to Test | How | API Keys Needed |
|-------|-------------|-----|-----------------|
| Comparison engine | Every field strategy, every edge case | Parametrized pytest | No |
| Normalization | Whitespace, unicode, numeric extraction | Parametrized pytest | No |
| Pydantic schemas | Validation, serialization | Unit tests | No |
| API endpoints | Status codes, response shapes, validation errors | FastAPI TestClient with mocked services | No |
| GPT response parsing | Valid, partial, malformed, error responses | Unit tests with fixture JSON | No |
| Full pipeline | End-to-end single label, processing time, image quality | Integration tests with real images | Yes |
| Batch processing | Concurrent processing, progress tracking, error handling | Integration tests | Yes |

See `docs/testing.md` for the complete test case catalog and mocking strategy.
