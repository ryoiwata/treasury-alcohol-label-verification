# Testing Rules

## Philosophy

Test what matters for a prototype that will be evaluated on verification accuracy and engineering rigor. The test suite is a key signal — the Treasury evaluators care about whether you can build testable, auditable AI systems for government compliance work.

**Test rigorously:** Comparison engine (all field strategies), text normalization, Pydantic schema validation, API endpoint wiring, GPT response parsing.
**Test lightly:** Frontend components, Docker configuration, database queries.
**Don't test:** Azure AI Vision's OCR accuracy (trust the service), OpenAI's response format (mock it), SQLite's query engine (trust SQLAlchemy).

Target: Every comparison strategy has parametrized tests. Normalization covers edge cases. API endpoints return correct status codes and response shapes. All deterministic tests pass without API keys.

## Framework

- **Python:** pytest with fixtures in `conftest.py`. No unittest classes.
- **Assertions:** Use plain `assert` statements with descriptive messages: `assert result.status == "MATCH", f"Expected MATCH for identical brand names, got {result.status}"`.
- **Parametrized tests:** Use `@pytest.mark.parametrize` for table-driven cases.
- **Markers:** `@pytest.mark.integration` for tests needing API keys.
- **Run all:** `pytest tests/ -v`
- **Run specific:** `pytest tests/test_comparator.py -v`
- **Deterministic only:** `pytest tests/ -v -m "not integration"`

## Directory Structure

```
backend/
├── tests/
│   ├── conftest.py              # Shared fixtures: test client, mock services, sample data
│   ├── test_comparator.py       # Comparison engine — the critical test file
│   ├── test_normalization.py    # Text normalization edge cases
│   ├── test_parser.py           # GPT response parsing and field extraction
│   ├── test_schemas.py          # Pydantic model validation
│   ├── test_api.py              # FastAPI endpoint tests with TestClient
│   ├── test_ocr.py              # OCR service (integration, needs Azure key)
│   ├── test_pipeline.py         # Full end-to-end pipeline (integration)
│   └── fixtures/
│       ├── ocr_output/
│       │   ├── bourbon_clean.json        # OCR result for clean bourbon label
│       │   ├── wine_angled.json          # OCR result for angled wine label
│       │   └── beer_glare.json           # OCR result for label with glare
│       ├── gpt_responses/
│       │   ├── valid_extraction.json      # Well-formed field extraction
│       │   ├── partial_extraction.json    # Missing optional fields
│       │   ├── malformed_response.json    # Edge case: unexpected format
│       │   └── error_response.json        # API error fixture
│       └── application_data/
│           ├── bourbon_application.json   # Matching application for bourbon label
│           ├── wine_application.json
│           └── mismatch_application.json  # Intentional mismatches for testing
├── test_labels/
│   ├── bourbon_clean.png
│   ├── wine_angled.jpg
│   └── beer_glare.jpg
```

## Required Test Cases

### Comparison Engine — Field Strategies (Deterministic, Critical)

This is the core of the testing strategy. Every comparison strategy is a pure function with zero API calls, zero flakiness.

#### 1. Warning Statement — Exact Match

```python
@pytest.mark.parametrize("extracted,expected,want_status", [
    # Exact match
    (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
        "MATCH",
    ),
    # Title case header — MUST be rejected (Jenny Park's requirement)
    (
        "Government Warning: (1) According to the Surgeon General...",
        "GOVERNMENT WARNING: (1) According to the Surgeon General...",
        "MISMATCH",
    ),
    # Extra whitespace — should normalize and match
    (
        "GOVERNMENT WARNING:  (1)  According  to  the  Surgeon  General...",
        "GOVERNMENT WARNING: (1) According to the Surgeon General...",
        "MATCH",
    ),
    # Missing warning entirely
    ("", "GOVERNMENT WARNING: ...", "NOT_FOUND"),
    # Truncated warning
    (
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink",
        "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
        "MISMATCH",
    ),
])
def test_compare_warning_statement(extracted, expected, want_status):
    result = compare_warning_statement(extracted, expected)
    assert result.status == want_status
```

#### 2. Brand Name — Fuzzy Match

```python
@pytest.mark.parametrize("extracted,expected,want_status", [
    # Identical
    ("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", "MATCH"),
    # Case difference only (Dave Morrison's STONE'S THROW case)
    ("STONE'S THROW", "Stone's Throw", "MATCH"),
    # Minor OCR artifact
    ("OLD TOM DISTILLERV", "OLD TOM DISTILLERY", "WARNING"),
    # Genuinely different
    ("MOUNTAIN CREEK", "OLD TOM DISTILLERY", "MISMATCH"),
    # Empty extraction
    ("", "OLD TOM DISTILLERY", "NOT_FOUND"),
    # Punctuation variation
    ("STONES THROW", "Stone's Throw", "WARNING"),
    # Unicode apostrophe vs ASCII
    ("STONE\u2019S THROW", "Stone's Throw", "MATCH"),
])
def test_compare_brand_name(extracted, expected, want_status):
    result = compare_brand_name(extracted, expected)
    assert result.status == want_status
```

#### 3. ABV — Numeric Extraction

```python
@pytest.mark.parametrize("extracted,expected,want_status", [
    # Standard format
    ("45% Alc./Vol. (90 Proof)", "45", "MATCH"),
    # Decimal
    ("13.5% Alc./Vol.", "13.5", "MATCH"),
    # Just the number on label
    ("45%", "45", "MATCH"),
    # Mismatch
    ("40% Alc./Vol.", "45", "MISMATCH"),
    # Close but not equal (within 0.5% tolerance? — design decision)
    ("44.8% Alc./Vol.", "45", "WARNING"),
    # Not found
    ("", "45", "NOT_FOUND"),
    # Proof only (should extract ABV from proof)
    ("90 Proof", "45", "MATCH"),
])
def test_compare_abv(extracted, expected, want_status):
    result = compare_abv(extracted, expected)
    assert result.status == want_status
```

#### 4. Net Contents — Unit Normalization

```python
@pytest.mark.parametrize("extracted,expected,want_status", [
    ("750 mL", "750 mL", "MATCH"),
    ("750ml", "750 mL", "MATCH"),
    ("750 ML", "750 mL", "MATCH"),
    ("1 L", "1000 mL", "MATCH"),
    ("1.75L", "1.75 L", "MATCH"),
    ("500 mL", "750 mL", "MISMATCH"),
    ("", "750 mL", "NOT_FOUND"),
])
def test_compare_net_contents(extracted, expected, want_status):
    result = compare_net_contents(extracted, expected)
    assert result.status == want_status
```

#### 5. Generic Text Fields (class_type, origin)

```python
@pytest.mark.parametrize("extracted,expected,want_status", [
    ("Kentucky Straight Bourbon Whiskey", "Kentucky Straight Bourbon Whiskey", "MATCH"),
    ("kentucky straight bourbon whiskey", "Kentucky Straight Bourbon Whiskey", "MATCH"),
    ("Kentucky Straight Bourbon", "Kentucky Straight Bourbon Whiskey", "WARNING"),
    ("Vodka", "Kentucky Straight Bourbon Whiskey", "MISMATCH"),
    ("", "Kentucky Straight Bourbon Whiskey", "NOT_FOUND"),
])
def test_compare_class_type(extracted, expected, want_status):
    result = compare_text_field(extracted, expected, field_name="class_type")
    assert result.status == want_status
```

### Text Normalization (Deterministic)

#### 6. Whitespace Normalization

```python
@pytest.mark.parametrize("input_text,expected", [
    ("  hello   world  ", "hello world"),
    ("hello\n\nworld", "hello world"),
    ("hello\tworld", "hello world"),
    ("", ""),
])
def test_normalize_whitespace(input_text, expected):
    assert normalize_whitespace(input_text) == expected
```

#### 7. Case Normalization

- Verify `normalize_for_comparison` lowercases consistently.
- Verify it preserves "GOVERNMENT WARNING:" detection before normalizing.

#### 8. Punctuation Normalization

- Unicode smart quotes → ASCII equivalents.
- Em dashes → hyphens.
- Curly apostrophes → straight apostrophes.

#### 9. Numeric Extraction

```python
@pytest.mark.parametrize("input_text,expected", [
    ("45% Alc./Vol. (90 Proof)", 45.0),
    ("13.5%", 13.5),
    ("90 Proof", 45.0),  # proof / 2
    ("750 mL", 750.0),
    ("no numbers here", None),
])
def test_extract_numeric(input_text, expected):
    assert extract_numeric_value(input_text) == expected
```

### GPT Response Parsing (Deterministic)

#### 10. Valid Extraction Response

```python
def test_parse_valid_gpt_response():
    fixture = load_fixture("gpt_responses/valid_extraction.json")
    result = parse_gpt_extraction(fixture)
    assert result.brand_name is not None
    assert result.abv is not None
    assert result.warning_statement is not None
```

#### 11. Partial Extraction (Missing Optional Fields)

- Parse response where `origin` or `producer` is missing.
- Assert: mandatory fields present, optional fields are None, no exception raised.

#### 12. Malformed Response Handling

- Parse response with unexpected JSON structure.
- Assert: raises `ParserError` with context, does not crash.

#### 13. Error Response Handling

- Parse API error response (rate limit, auth failure).
- Assert: raises appropriate exception with status code context.

### Pydantic Schema Validation (Deterministic)

#### 14. ApplicationData Validation

```python
def test_application_data_valid():
    data = ApplicationData(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45",
        net_contents="750 mL",
        warning_statement="GOVERNMENT WARNING: ...",
    )
    assert data.brand_name == "OLD TOM DISTILLERY"

def test_application_data_missing_required():
    with pytest.raises(ValidationError):
        ApplicationData(brand_name="", abv="45")  # missing required fields
```

#### 15. VerificationResult Serialization

- Create a `VerificationResult` with all field statuses, serialize to JSON.
- Assert: JSON matches expected API response shape.
- Assert: `status` field uses Literal types correctly.

### API Endpoint Tests (Deterministic with Mocks)

#### 16. POST /api/verify — Happy Path

```python
def test_verify_endpoint_success(test_client, mock_ocr, mock_parser):
    mock_ocr.return_value = "OLD TOM DISTILLERY Kentucky Straight Bourbon..."
    mock_parser.return_value = ExtractedFields(brand_name="OLD TOM DISTILLERY", ...)
    
    response = test_client.post("/api/verify", files={"file": ...}, data={"application_data": ...})
    assert response.status_code == 200
    result = response.json()
    assert "fields" in result
    assert result["processing_time_ms"] > 0
```

#### 17. POST /api/verify — Invalid File Type

- Upload a `.txt` file.
- Assert: 400 response with descriptive error message.

#### 18. POST /api/verify — Missing Application Data

- Upload image without application_data.
- Assert: 422 (validation error) with field-level error details.

#### 19. POST /api/batch — Batch Upload

- Upload 3 files with matching application data.
- Assert: 202 response with `batch_id`.

#### 20. GET /api/batch/{id} — Status Polling

- Assert: returns "processing" for in-progress, "complete" with results for finished.
- Assert: 404 for nonexistent batch ID.

#### 21. GET /api/history — Paginated Results

- Insert test verification records.
- Assert: returns paginated results with correct count and ordering.

#### 22. Path Traversal Prevention

- Request `/api/verify` with a filename containing `../../etc/passwd`.
- Assert: 400 response, file is rejected.

### Full Pipeline (Integration — needs API keys)

#### 23. End-to-End Single Label

```python
@pytest.mark.integration
def test_full_pipeline_bourbon_label():
    if not os.getenv("AZURE_VISION_KEY") or not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Requires AZURE_VISION_KEY and OPENAI_API_KEY")
    
    with open("test_labels/bourbon_clean.png", "rb") as f:
        result = verify_label(f, BOURBON_APPLICATION_DATA)
    
    assert result.processing_time_ms < 5000  # 5-second requirement
    assert result.fields["brand_name"].status in ("MATCH", "WARNING")
    assert result.fields["warning_statement"].status in ("MATCH", "MISMATCH")  # must produce a verdict
```

#### 24. Processing Time Budget

- Run 5 single-label verifications sequentially.
- Assert: average processing time under 5 seconds.
- Log individual timings for performance tracking.

#### 25. Image Quality Handling

- Submit label with known glare/angle issues.
- Assert: system returns results (possibly with lower confidence) rather than crashing.
- Assert: `image_quality.issues` list is populated when applicable.

## Mocking Strategy

### OCR Service Mock (for endpoint tests)

```python
@pytest.fixture
def mock_ocr_service(mocker):
    mock = mocker.patch("app.services.ocr.OCRService.extract_text")
    mock.return_value = OCRResult(
        text="OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n45% Alc./Vol. (90 Proof)\n750 mL\nGOVERNMENT WARNING: ...",
        confidence=0.95,
        bounding_boxes=[],
    )
    return mock
```

### GPT Parser Mock (for endpoint tests)

```python
@pytest.fixture
def mock_parser_service(mocker):
    mock = mocker.patch("app.services.parser.GPTParser.extract_fields")
    mock.return_value = ExtractedFields(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        warning_statement="GOVERNMENT WARNING: (1) According to the Surgeon General...",
        producer="Old Tom Distillery, Louisville, KY",
        origin="United States",
    )
    return mock
```

### Test Client Fixture

```python
@pytest.fixture
def test_client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)
```

## What Not to Test

- Don't test Azure AI Vision's OCR accuracy — it's Microsoft's service. Mock it.
- Don't test OpenAI's response format — trust the API spec. Mock it.
- Don't test SQLAlchemy's query engine — trust the ORM. Test your query logic if complex.
- Don't test Pydantic's validation engine — trust the library. Test your model definitions.
- Don't test React components for a prototype — the Python backend tests cover correctness.
- Don't aim for 100% coverage — aim for "every comparison strategy works, every edge case is covered, API endpoints return correct shapes, and the pipeline stays under 5 seconds."

## Interview Talking Points

Be prepared to discuss these testing decisions:

1. **"How do you test the comparison engine?"**
   → Parametrized tests with fixture data covering every field strategy. Pure Python, zero API calls, zero flakiness. This is the most critical and most testable layer.

2. **"How do you test accuracy when OCR and GPT outputs are non-deterministic?"**
   → I separate extraction (non-deterministic, mocked in unit tests) from comparison (fully deterministic, exhaustively tested). Integration tests check the full pipeline but assert on properties (processing time, field presence) not exact values.

3. **"How do you handle the warning statement requirement?"**
   → Exact match after whitespace normalization, never fuzzy. Parametrized tests cover the specific case Jenny Park flagged — "Government Warning" in title case is always rejected. The test suite documents the requirement.

4. **"What about regression testing when you change the GPT prompt?"**
   → The comparison engine is prompt-independent. If GPT returns different field values, the comparison still works the same way. Integration tests catch extraction quality regressions.

5. **"How would you test this at scale in production?"**
   → Golden-file tests with a corpus of labeled reference images. Track extraction accuracy as a metric over time. A/B test prompt variations. But for the prototype, exhaustive comparison engine tests are the right granularity.
