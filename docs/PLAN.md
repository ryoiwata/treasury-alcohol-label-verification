# Implementation Plan — TTB Label Verification Tool

This is the phased build plan for the TTB Label Verification Tool. It is written for an
AI coding agent (OpenAI Codex) to execute **one phase at a time, in order, committing
after each phase**.

## How to use this plan

- Execute phases in numerical order. Do not start a phase until its **Depends on** phases are complete.
- Each phase is a single, self-contained unit of work that ends in a **committable, non-broken state**.
- **Tests are written in the same phase as the code they test.** Every phase that adds application code adds its tests, and the verification step requires `pytest` (for the relevant marker set) to pass.
- After each phase: run `ruff check .` and `ruff format .`, run the phase's tests, then `git add` and `git commit` with a Conventional Commit message (see AGENTS.md → Git Workflow).
- Authoritative references already in the repo: `AGENTS.md`, `README.md`, `docs/PRD.md`, `docs/SPEC.md`, and `docs/rules/{code-style,prompts,security,testing}.md`. This plan inlines the critical contracts so you do not have to cross-reference mid-implementation, but those files win if anything conflicts.

## Architecture recap (so each phase has context)

```
Label Image → Azure AI Vision (OCR) → GPT-4o (structuring) → Comparison Engine (pure Python) → Result
```

Three layers, built **inside-out**: the deterministic comparison engine and its supporting
utilities/types have zero dependencies and zero API calls — they are built and exhaustively
tested first. External services (Azure Vision, OpenAI) sit behind interfaces that are mocked
in unit tests and only wired to real APIs in later, isolatable phases. The frontend is last
because it consumes a working API.

## Phase dependency graph

```
Phase 1 (scaffold)
   └─ Phase 2 (schemas + constants)
        ├─ Phase 3 (normalization)
        │     └─ Phase 4 (comparison engine)   ← most critical code
        │           └─ Phase 5 (service interfaces + stubs)
        │                 └─ Phase 6 (FastAPI app + endpoints, stubbed services)
        │                       ├─ Phase 7 (Azure Vision real OCR)
        │                       ├─ Phase 8 (GPT-4o real parser)
        │                       ├─ Phase 9 (SQLite + history)
        │                       │     └─ Phase 10 (batch processing)
        │                       └─ Phase 11 (React frontend)
        │                             └─ Phase 12 (Docker + deployment)
```

---

## Phase 1: Project Scaffolding & Configuration

**Goal:** The repository has its full directory skeleton, pinned dependencies, environment
templates, ignore rules, and a config loader that fails fast on missing env vars — and the
backend package imports cleanly.

**Depends on:** none.

**Files to create:**

- `.gitignore` (repo root)
- `Makefile` (repo root)
- `backend/requirements.txt`
- `backend/.env.example`
- `backend/pyproject.toml` (ruff + pytest + mypy config)
- `backend/app/__init__.py`
- `backend/app/config.py`
- `backend/app/routers/__init__.py`
- `backend/app/services/__init__.py`
- `backend/app/models/__init__.py`
- `backend/app/utils/__init__.py`
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` (placeholder, expanded in later phases)
- `backend/tests/test_config.py`
- `frontend/.env.example`
- `frontend/.gitignore` (or rely on root — see step 2)

**Implementation steps:**

1. Create the directory structure exactly as in SPEC.md §2.1 and AGENTS.md → Project Structure. Add empty `__init__.py` files to every Python package directory (`app`, `app/routers`, `app/services`, `app/models`, `app/utils`, `tests`).

2. Create `.gitignore` at the repo root with **exactly** the contents from `docs/rules/security.md` → .gitignore section:

   ```gitignore
   # Secrets
   .env
   .env.*
   *.pem
   *.key

   # Python
   __pycache__/
   *.pyc
   .pytest_cache/
   *.egg-info/
   venv/
   .venv/
   dist/
   build/

   # Database
   *.db
   *.sqlite3

   # Frontend
   node_modules/
   frontend/dist/

   # IDE
   .vscode/
   .idea/

   # OS
   .DS_Store
   Thumbs.db

   # Large test files
   test_labels/*.tiff
   test_labels/raw/
   ```

   Add a negation line so `.env.example` files are NOT ignored: `!.env.example`.

3. Create `backend/requirements.txt` with exact pinned versions:

   ```
   fastapi==0.115.6
   uvicorn[standard]==0.34.0
   httpx==0.28.1
   python-multipart==0.0.20
   pydantic==2.10.4
   sqlalchemy==2.0.36
   fuzzywuzzy==0.18.0
   python-Levenshtein==0.26.1
   Pillow==11.1.0
   python-dotenv==1.0.1

   # Dev / test
   pytest==8.3.4
   pytest-asyncio==0.25.2
   pytest-mock==3.14.0
   ruff==0.9.2
   mypy==1.14.1
   respx==0.22.0
   ```

   > `respx` mocks `httpx` calls in service unit tests. `pytest-asyncio` runs async tests.

4. Create `backend/.env.example` (committed; the real `.env` is gitignored):

   ```
   AZURE_VISION_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
   AZURE_VISION_KEY=<your-azure-vision-key>
   OPENAI_API_KEY=<your-openai-key>
   DATABASE_URL=sqlite:///./verification.db
   LOG_LEVEL=info
   MAX_BATCH_SIZE=50
   MATCH_THRESHOLD=0.95
   WARNING_THRESHOLD=0.85
   FRONTEND_URL=http://localhost:5173
   ```

5. Create `frontend/.env.example`:

   ```
   VITE_API_URL=http://localhost:8000
   ```

6. Create `backend/pyproject.toml` configuring ruff (line length 88, isort import grouping stdlib→third-party→local), pytest (register the `integration` marker, set `asyncio_mode = "auto"`, testpaths `tests`), and mypy (target `app/`). Example:

   ```toml
   [tool.ruff]
   line-length = 88
   target-version = "py311"

   [tool.ruff.lint]
   select = ["E", "F", "I", "UP", "B"]

   [tool.ruff.lint.isort]
   known-first-party = ["app"]

   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   testpaths = ["tests"]
   markers = [
       "integration: tests that require real API keys (Azure Vision, OpenAI)",
   ]

   [tool.mypy]
   python_version = "3.11"
   files = ["app"]
   ignore_missing_imports = true
   ```

7. Create `app/config.py`. It must expose `get_required_env(name) -> str` (raises `RuntimeError` if empty, per security.rules), an `AppConfig` frozen dataclass (SPEC.md §2.3), and `load_and_validate_config() -> AppConfig` which reads env via `python-dotenv`, builds the embedded `ComparisonConfig` from `MATCH_THRESHOLD` / `WARNING_THRESHOLD` (falling back to the `constants.py` defaults added in Phase 2 — for Phase 1 use literal defaults `0.95` / `0.85` / `0.5` and a TODO comment to source them from constants in Phase 2), and **fails fast** if any required var is missing. Note: `ComparisonConfig` is also defined in Phase 2's `comparator` types; for Phase 1, define a minimal local placeholder dataclass in `config.py` if needed, and refactor in Phase 2 to import the canonical one. Required vars: `AZURE_VISION_ENDPOINT`, `AZURE_VISION_KEY`, `OPENAI_API_KEY`. Optional with defaults per SPEC.md §2.3.

   `AppConfig` fields (SPEC.md §2.3):

   ```python
   @dataclass(frozen=True)
   class AppConfig:
       azure_vision_endpoint: str
       azure_vision_key: str
       openai_api_key: str
       database_url: str = "sqlite:///./verification.db"
       log_level: str = "info"
       max_batch_size: int = 50
       max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
       ocr_timeout_seconds: float = 30.0
       gpt_timeout_seconds: float = 60.0
       ocr_concurrency_limit: int = 5
       gpt_concurrency_limit: int = 3
       comparison_config: "ComparisonConfig" = field(default_factory=ComparisonConfig)
   ```

   **Never log key values** — log only `bool(value)` presence.

8. Create `backend/tests/test_config.py`: assert `get_required_env` raises `RuntimeError` when a var is empty/unset (use `monkeypatch.delenv` / `setenv`), and that `load_and_validate_config()` succeeds when all required vars are set and applies defaults for optional ones.

9. Create `Makefile` at repo root with the standard targets from `code-style.rules` → Makefile.

10. Create a placeholder `backend/tests/conftest.py` with a module docstring and any trivial shared imports (real fixtures arrive in later phases).

**Verification:**

- `cd backend && python -c "import app.config"` succeeds.
- `cd backend && pytest tests/test_config.py -v` passes.
- `cd backend && ruff check . && ruff format --check .` clean.
- `git status` shows no `.env` or `__pycache__` staged.

**Commit:** `chore(scaffold): add project structure, pinned deps, env templates, config loader`

---

## Phase 2: Pydantic Models & Constants

**Goal:** All request/response Pydantic models, comparison-engine dataclasses, the government
warning constant, field-strategy mapping, and limits exist and validate correctly.

**Depends on:** Phase 1.

**Files to create:**

- `backend/app/models/schemas.py`
- `backend/app/utils/constants.py`
- `backend/tests/test_schemas.py`

**Files to modify:**

- `backend/app/config.py` (import the canonical `ComparisonConfig` and constant defaults from `constants.py`, removing the Phase 1 placeholder).

**Implementation steps:**

1. Create `app/utils/constants.py` with **exactly** these contents (from prompts.rules → Constants):

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

2. Create `app/models/schemas.py` with **exactly** the models from prompts.rules → Pydantic Models. Copy verbatim:

   ```python
   from datetime import datetime
   from typing import Literal

   from pydantic import BaseModel, ConfigDict, Field


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


   class HistoryResponse(BaseModel):
       """Paginated history query response."""
       total: int
       limit: int
       offset: int
       results: list[VerificationResult]


   class ErrorResponse(BaseModel):
       """Standard error response."""
       error: str
       detail: str | None = None
   ```

   > `HistoryResponse` is added (not in prompts.rules but implied by SPEC.md §4.4 response shape) so the history endpoint has a typed response model.

3. Add the comparison-engine dataclasses. Per SPEC.md these live in `comparator.py`, but `config.py` needs `ComparisonConfig` and Phase 4 needs both. **Define them in `app/services/comparator.py` types now is premature (comparator built in Phase 4).** Instead create them here is also awkward. Resolution: create a tiny module `app/services/comparator_types.py`? No — keep SPEC structure. Define `ComparisonConfig` and `ComparisonResult` at the **top of a new file `app/services/comparator.py`** in this phase as a types-only stub (no logic yet), and import `ComparisonConfig` into `config.py`. The comparison logic itself is added in Phase 4. Contents:

   ```python
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
   ```

4. Update `app/config.py`: import `ComparisonConfig` from `app.services.comparator` and `DEFAULT_*` from `app.utils.constants`; remove the Phase 1 placeholder; build `comparison_config` from env (`MATCH_THRESHOLD`, `WARNING_THRESHOLD`) defaulting to the constants.

5. Create `backend/tests/test_schemas.py` covering testing.rules cases #14 and #15:
   - `test_application_data_valid` — construct a full valid `ApplicationData`, assert fields.
   - `test_application_data_missing_required` — `with pytest.raises(ValidationError): ApplicationData(brand_name="", abv="45")`.
   - `test_application_data_extra_forbidden` — passing an unexpected field raises `ValidationError` (proves `extra="forbid"`).
   - `test_verification_result_serialization` — build a `VerificationResult` with one of each status across fields, `model_dump_json()`, reload, assert shape and that `status`/`method` Literals serialize as plain strings.

**Verification:**

- `cd backend && pytest tests/test_schemas.py tests/test_config.py -v` passes.
- `cd backend && python -c "from app.models.schemas import VerificationResult; from app.services.comparator import ComparisonConfig; from app.utils.constants import GOVERNMENT_WARNING_TEXT"` succeeds.
- `ruff check . && ruff format --check .` clean.

**Commit:** `feat(models): add pydantic schemas, comparison types, and constants`

---

## Phase 3: Text Normalization Utilities + Tests

**Goal:** Every normalization and numeric-extraction function from SPEC.md §7 exists, is pure
and stateless, and is covered by parametrized tests.

**Depends on:** Phase 1 (Phase 2 not strictly required, but build after it).

**Files to create/modify:**

- `backend/app/utils/normalization.py`
- `backend/tests/test_normalization.py`

**Implementation steps:**

1. Create `app/utils/normalization.py` with **exactly** the functions from SPEC.md §7, all with explicit return type hints and docstrings:

   ```python
   import re


   def normalize_whitespace(text: str) -> str:
       """Collapse all runs of whitespace to single space, strip edges."""
       return " ".join(text.split())


   def normalize_unicode_punctuation(text: str) -> str:
       """Replace smart quotes, em dashes, etc. with ASCII equivalents."""
       replacements = {
           "‘": "'", "’": "'",
           "“": '"', "”": '"',
           "–": "-", "—": "-",
           "…": "...",
       }
       for unicode_char, ascii_char in replacements.items():
           text = text.replace(unicode_char, ascii_char)
       return text


   def normalize_for_fuzzy_comparison(text: str) -> str:
       """Lowercase, normalize whitespace, normalize unicode punctuation."""
       text = text.lower()
       text = normalize_whitespace(text)
       text = normalize_unicode_punctuation(text)
       return text


   def extract_abv_numeric(text: str) -> float | None:
       """Extract ABV percentage from various formats."""
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
       """Extract volume in mL from various formats."""
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


   def strip_punctuation(text: str) -> str:
       """Remove punctuation for normalized string comparison."""
       return re.sub(r"[^\w\s]", "", text)


   def normalize_string(text: str) -> str:
       """Normalized-match pipeline: lowercase, collapse whitespace, strip punctuation."""
       text = normalize_for_fuzzy_comparison(text)
       text = strip_punctuation(text)
       return normalize_whitespace(text)
   ```

   > `extract_abv_numeric` / `extract_volume_ml` are the numeric extractors used by the comparator. The generic `extract_numeric_value` referenced in testing.rules case #9 is an alias that dispatches: implement it as `extract_numeric_value(text) -> float | None` returning `extract_abv_numeric(text)` for ABV/proof/percent and falling through to a bare-number/volume path — OR keep two named extractors and have the comparator pick. **Decision:** keep `extract_abv_numeric` and `extract_volume_ml` as the canonical extractors; additionally add `extract_numeric_value(text)` that tries ABV-style first (`%`/proof), then volume, then bare number, so testing.rules case #9 passes as written.

2. Create `backend/tests/test_normalization.py` with parametrized tests. Seed with at least these (from testing.rules #6–#9); Codex should add more edge cases:

   ```python
   import pytest

   from app.utils.normalization import (
       extract_abv_numeric,
       extract_numeric_value,
       extract_volume_ml,
       normalize_unicode_punctuation,
       normalize_whitespace,
   )


   @pytest.mark.parametrize("input_text,expected", [
       ("  hello   world  ", "hello world"),
       ("hello\n\nworld", "hello world"),
       ("hello\tworld", "hello world"),
       ("", ""),
   ])
   def test_normalize_whitespace(input_text, expected):
       assert normalize_whitespace(input_text) == expected


   @pytest.mark.parametrize("input_text,expected", [
       ("‘quoted’", "'quoted'"),
       ("“quoted”", '"quoted"'),
       ("a – b", "a - b"),
       ("a — b", "a - b"),
       ("etc…", "etc..."),
   ])
   def test_normalize_unicode_punctuation(input_text, expected):
       assert normalize_unicode_punctuation(input_text) == expected


   @pytest.mark.parametrize("input_text,expected", [
       ("45% Alc./Vol. (90 Proof)", 45.0),
       ("13.5%", 13.5),
       ("90 Proof", 45.0),
       ("no numbers here", None),
   ])
   def test_extract_abv_numeric(input_text, expected):
       assert extract_abv_numeric(input_text) == expected


   @pytest.mark.parametrize("input_text,expected", [
       ("750 mL", 750.0),
       ("750ml", 750.0),
       ("1 L", 1000.0),
       ("1.75L", 1750.0),
       ("no numbers here", None),
   ])
   def test_extract_volume_ml(input_text, expected):
       assert extract_volume_ml(input_text) == expected


   @pytest.mark.parametrize("input_text,expected", [
       ("45% Alc./Vol. (90 Proof)", 45.0),
       ("13.5%", 13.5),
       ("90 Proof", 45.0),
       ("750 mL", 750.0),
       ("no numbers here", None),
   ])
   def test_extract_numeric_value(input_text, expected):
       assert extract_numeric_value(input_text) == expected
   ```

   Note the floating-point tolerance: for `extract_volume_ml` of oz values use `pytest.approx`.

**Verification:**

- `cd backend && pytest tests/test_normalization.py -v` passes.
- `ruff check . && ruff format --check .` clean.

**Commit:** `feat(utils): add text normalization and numeric extraction helpers`

---

## Phase 4: Comparison Engine + Tests (most critical phase)

**Goal:** The `Comparator` class implements every field strategy from SPEC.md §3.3, derives
the overall verdict, contains zero I/O and zero API calls, and is exhaustively covered by
parametrized tests including every case in testing.rules.

**Depends on:** Phase 2 (schemas, `ComparisonConfig`/`ComparisonResult`, constants), Phase 3 (normalization).

**Files to modify/create:**

- `backend/app/services/comparator.py` (extend the Phase 2 types stub with the engine)
- `backend/tests/test_comparator.py`

**Critical constraints (from AGENTS.md + code-style.rules):**

- This file is **pure Python with zero API calls. The boundary is sacred.**
- Warning statement comparison is **exact match after whitespace normalization — never fuzzy**, and **case is NOT normalized** ("GOVERNMENT WARNING:" vs "Government Warning:" must be MISMATCH).
- ABV comparison **extracts numeric values before comparing**.
- Fuzzy thresholds come from `config`, never hardcoded.

**Implementation steps:**

1. In `app/services/comparator.py`, keep the `ComparisonConfig` / `ComparisonResult` dataclasses from Phase 2 and add the `Comparator` class implementing the SPEC.md §3.3 interface. Module-level imports: `from fuzzywuzzy import fuzz`, normalization helpers, schemas (`ExtractedFields`, `ApplicationData`, `FieldComparison`), constants (`FIELD_STRATEGIES`).

   Method signatures (SPEC.md §3.3):

   ```python
   class Comparator:
       def __init__(self, config: ComparisonConfig): ...
       def compare_all(self, extracted: ExtractedFields, expected: ApplicationData) -> list[FieldComparison]: ...
       def compare_warning_statement(self, extracted: str | None, expected: str) -> FieldComparison: ...
       def compare_brand_name(self, extracted: str | None, expected: str) -> FieldComparison: ...
       def compare_abv(self, extracted: str | None, expected: str) -> FieldComparison: ...
       def compare_net_contents(self, extracted: str | None, expected: str) -> FieldComparison: ...
       def compare_text_field(self, extracted: str | None, expected: str, field_name: str) -> FieldComparison: ...
   ```

   Each `compare_*` returns a `FieldComparison` (the Pydantic model — the public API type). Set `field`, `status`, `extracted`, `expected`, `method`, `similarity`, `note` appropriately.

2. **Exact Match — `compare_warning_statement`** (`method="exact_match"`), per SPEC.md §3.3.1:
   1. If `extracted` is `None` or empty/whitespace-only → `NOT_FOUND`, note "Warning statement not found on label".
   2. `normalize_whitespace` BOTH values (do NOT lowercase).
   3. Equal → `MATCH`. Different → `MISMATCH`.
   4. Generate a specific note. Detect the common case: if the two match case-insensitively but not case-sensitively, note "Header not in required ALL CAPS format" (covers Jenny Park's case). If extracted is a strict prefix of expected (or much shorter), note "Warning statement appears truncated".

3. **Fuzzy Match — `compare_brand_name`** (and reused by `producer`) (`method="fuzzy_match"`):
   1. None/empty → `NOT_FOUND`.
   2. `normalize_for_fuzzy_comparison` both.
   3. `ratio = fuzz.ratio(norm_extracted, norm_expected) / 100.0`.
   4. `ratio >= config.match_threshold` → `MATCH`; `>= config.warning_threshold` → `WARNING`; else `MISMATCH`.
   5. Set `similarity = round(ratio, 2)`. Note describes the difference ("Case difference only" when normalized forms are equal, "Minor character variation" for near matches, etc.).

4. **Numeric Match — `compare_abv`** (`method="numeric_match"`):
   1. None/empty → `NOT_FOUND`.
   2. `extracted_num = extract_abv_numeric(extracted)`, `expected_num = extract_abv_numeric(expected)`. If either is `None` → `MISMATCH` with note "Could not extract a numeric ABV value".
   3. `diff = abs(extracted_num - expected_num)`. `diff == 0` → `MATCH`; `0 < diff <= config.abv_tolerance` → `WARNING`; `diff > config.abv_tolerance` → `MISMATCH`.
   4. Note includes both numerics, e.g. "Extracted 44.8% vs expected 45% (within tolerance)".

5. **Numeric Match — `compare_net_contents`** (`method="numeric_match"`):
   1. None/empty → `NOT_FOUND`.
   2. `extract_volume_ml` both. If either `None` → `MISMATCH`.
   3. net_contents tolerance is **±0** (exact, per SPEC.md §3.3.1): equal mL → `MATCH`; else `MISMATCH`. (No WARNING band for volume.) Use `math.isclose` with a tiny abs_tol for float safety.
   4. Note includes both normalized mL values.

6. **Normalized String Match — `compare_text_field`** (class_type, origin) (`method="normalized_match"`):
   1. None/empty → `NOT_FOUND`.
   2. `normalize_string` both. Equal → `MATCH`.
   3. If not equal, fall back to fuzzy: `fuzz.ratio` on the normalized strings, apply the same thresholds (`>=match`→MATCH, `>=warning`→WARNING, else MISMATCH). Set `similarity`.
   4. Note describes the outcome.

7. **`compare_all`**: iterate `FIELD_STRATEGIES`, dispatch each field to the right method using the corresponding `expected.<field>` value. For optional fields (`producer`, `origin`) that are `None` in `ApplicationData`, skip them (do not emit a comparison) — only compare fields the application actually declared. Return the list in a stable field order (brand_name, class_type, abv, net_contents, warning_statement, producer, origin).

8. **`derive_overall_status`** — add as a module-level function exactly per SPEC.md §3.3.2:

   ```python
   def derive_overall_status(field_results: list[FieldComparison]) -> str:
       statuses = [f.status for f in field_results]
       if "MISMATCH" in statuses:
           return "FAIL"
       if "WARNING" in statuses or "NOT_FOUND" in statuses:
           return "REVIEW_NEEDED"
       return "PASS"
   ```

9. Create `backend/tests/test_comparator.py`. Include a module-level `Comparator(ComparisonConfig())` fixture or instantiate per test. Use thin wrappers so the testing.rules functions (`compare_warning_statement(extracted, expected)` etc.) work — either expose module-level wrappers that build a default `Comparator`, or adapt the tests to call methods on a fixture instance. **Decision:** add module-level convenience functions `compare_warning_statement`, `compare_brand_name`, `compare_abv`, `compare_net_contents`, `compare_text_field` that delegate to a default `Comparator(ComparisonConfig())`, so the testing.rules tests match verbatim.

   Include **all** parametrized tables from testing.rules §"Comparison Engine — Field Strategies":
   - `test_compare_warning_statement` (5 cases: exact match, title-case header → MISMATCH, extra whitespace → MATCH, empty → NOT_FOUND, truncated → MISMATCH).
   - `test_compare_brand_name` (7 cases: identical, case-only, OCR artifact → WARNING, different → MISMATCH, empty → NOT_FOUND, dropped apostrophe → WARNING, unicode apostrophe → MATCH).
   - `test_compare_abv` (7 cases: standard, decimal, bare %, mismatch, 44.8 → WARNING, empty → NOT_FOUND, proof-only → MATCH).
   - `test_compare_net_contents` (7 cases).
   - `test_compare_class_type` (5 cases via `compare_text_field`).

   Add a `test_derive_overall_status` covering: all MATCH → PASS; any WARNING/NOT_FOUND (no MISMATCH) → REVIEW_NEEDED; any MISMATCH → FAIL.

   > After implementing, run the brand-name fuzzy cases and confirm the default thresholds (0.95/0.85) actually produce the expected verdicts for the seed strings (e.g. "STONES THROW" vs "Stone's Throw" should land in the 0.85–0.94 WARNING band; "STONE'S THROW" vs "Stone's Throw" should be ≥0.95 MATCH after normalization). If a seed case lands on a boundary, do NOT change thresholds — adjust the note logic / verify normalization, and document any genuinely ambiguous case. Thresholds stay at spec defaults.

**Verification:**

- `cd backend && pytest tests/test_comparator.py -v` passes (all parametrized cases green).
- `cd backend && grep -rn "httpx\|requests\|openai\|azure\|async def" app/services/comparator.py` returns nothing — proves zero I/O in the engine.
- `ruff check . && ruff format --check . && mypy app/services/comparator.py` clean.

**Commit:** `feat(comparator): add deterministic field comparison engine with parametrized tests`

---

## Phase 5: Service Interfaces with Stubs

**Goal:** `OCRService`, `GPTParser`, and `VerificationPipeline` exist with their full method
signatures and supporting result types, returning deterministic stub/fixture data so the
pipeline runs end-to-end with no network calls. Custom exception classes are defined.

**Depends on:** Phase 4.

**Files to create:**

- `backend/app/services/exceptions.py`
- `backend/app/services/ocr.py` (stub)
- `backend/app/services/parser.py` (stub)
- `backend/app/services/pipeline.py`
- `backend/tests/fixtures/__init__.py`
- `backend/tests/fixtures/gpt_responses/valid_extraction.json`
- `backend/tests/fixtures/gpt_responses/partial_extraction.json`
- `backend/tests/fixtures/gpt_responses/malformed_response.json`
- `backend/tests/fixtures/gpt_responses/error_response.json`
- `backend/tests/fixtures/ocr_output/bourbon_clean.json`
- `backend/tests/fixtures/application_data/bourbon_application.json`
- `backend/tests/fixtures/application_data/mismatch_application.json`
- `backend/tests/test_pipeline.py` (the deterministic, stubbed pipeline test — the real-API integration test is added in later phases)

**Implementation steps:**

1. Create `app/services/exceptions.py` with the domain exceptions from code-style.rules:

   ```python
   class OCRExtractionError(Exception):
       """Raised when Azure AI Vision OCR fails."""


   class ParserError(Exception):
       """Raised when GPT field extraction fails or returns unparseable output."""


   class InvalidImageError(ValueError):
       """Raised when an uploaded file fails validation."""
   ```

2. Create `app/services/ocr.py` with the `OCRResult`, `OCRLine`, `Point` types and the `OCRService` class. Use Pydantic models (or dataclasses) for the result types — match SPEC.md §3.1:

   ```python
   class Point(BaseModel):
       x: float
       y: float

   class OCRLine(BaseModel):
       text: str
       confidence: float
       bounding_polygon: list[Point] = Field(default_factory=list)

   class OCRResult(BaseModel):
       text: str
       lines: list[OCRLine] = Field(default_factory=list)
       average_confidence: float = 0.0
       image_quality_issues: list[str] = Field(default_factory=list)
   ```

   `OCRService`:

   ```python
   class OCRService:
       def __init__(self, endpoint: str, key: str, timeout_seconds: float = 30.0): ...
       async def extract_text(self, image_bytes: bytes, content_type: str) -> OCRResult: ...
       async def close(self) -> None: ...
   ```

   **Phase 5 stub behavior:** `extract_text` ignores the bytes and returns a fixed `OCRResult` built from `tests/fixtures/ocr_output/bourbon_clean.json`-equivalent text (a realistic multi-line bourbon label OCR dump including the full government warning), `average_confidence=0.95`, no issues. Add a `# STUB:` comment marking where the real Azure call goes in Phase 7. `__init__` stores endpoint/key/timeout but does NOT create an httpx client yet (added Phase 7). `close()` is a no-op for now.

3. Create `app/services/parser.py` with the `GPTParser` class:

   ```python
   class GPTParser:
       def __init__(self, api_key: str, timeout_seconds: float = 60.0): ...
       async def extract_fields(self, ocr_text: str) -> ExtractedFields: ...
       async def close(self) -> None: ...
   ```

   Also create a pure, deterministic helper `parse_gpt_extraction(response_json: dict) -> ExtractedFields` that takes a raw OpenAI response dict, reads `choices[0].message.content`, parses it as JSON, and maps to `ExtractedFields` (missing keys → `None`). On JSON-parse failure raise `ParserError("GPT returned non-JSON response")`. On missing `choices` structure raise `ParserError`. This helper is what unit tests target (testing.rules #10–#13).

   **Phase 5 stub behavior for `extract_fields`:** ignore `ocr_text`, return a fixed `ExtractedFields` matching the stub OCR (brand "OLD TOM DISTILLERY", etc.). Mark `# STUB:` for the Phase 8 real call.

4. Create `app/services/pipeline.py` implementing `VerificationPipeline` **exactly** per SPEC.md §3.4 (constructor takes `ocr`, `parser`, `comparator`; `verify()` times the run with `time.monotonic()`, runs OCR → parse → `comparator.compare_all`, derives status, builds `VerificationResult` with `id=f"ver_{uuid4().hex[:12]}"` and `ImageQuality`). Copy the SPEC.md §3.4 body.

5. Create the fixture JSON files:
   - `gpt_responses/valid_extraction.json` — a realistic OpenAI chat completion response whose `choices[0].message.content` is a JSON string with all 7 fields populated (bourbon label).
   - `gpt_responses/partial_extraction.json` — content JSON with `producer` and `origin` missing/null.
   - `gpt_responses/malformed_response.json` — `choices[0].message.content` is `"not json at all {"`.
   - `gpt_responses/error_response.json` — an OpenAI-style error body (`{"error": {"message": "Rate limit", "code": "rate_limit_exceeded"}}`).
   - `ocr_output/bourbon_clean.json` — serialized `OCRResult` for a clean bourbon label.
   - `application_data/bourbon_application.json` — matching `ApplicationData`.
   - `application_data/mismatch_application.json` — deliberately wrong brand/warning for FAIL-path tests.

6. Create `backend/tests/test_pipeline.py` (deterministic, no API keys): construct `VerificationPipeline(OCRService(...stub...), GPTParser(...stub...), Comparator(ComparisonConfig()))`, call `await pipeline.verify(b"fakebytes", "image/png", bourbon_application_data)`, and assert: `result.id` starts with `ver_`, `result.processing_time_ms >= 0`, `result.status` is one of the three literals, `result.fields` is non-empty, and `result.image_quality.readable is True`. Add a second test using `mismatch_application.json` asserting `result.status == "FAIL"`.

7. Add a `parse_gpt_extraction` test set to `backend/tests/test_parser.py` (create it now — deterministic part only): load each `gpt_responses` fixture and assert testing.rules #10–#13 behavior (valid → fields present; partial → optionals None, no raise; malformed → raises `ParserError`; error response → raises `ParserError`). The real-API `extract_fields` integration test is deferred to Phase 8.

**Verification:**

- `cd backend && pytest tests/test_pipeline.py tests/test_parser.py -v` passes with no network access.
- `cd backend && python -c "from app.services.pipeline import VerificationPipeline; from app.services.ocr import OCRService; from app.services.parser import GPTParser"` succeeds.
- `ruff check . && ruff format --check .` clean.

**Commit:** `feat(services): add OCR, parser, pipeline interfaces with deterministic stubs`

---

## Phase 6: FastAPI App + API Endpoints + Tests (stubbed services)

**Goal:** The FastAPI app boots, exposes `/api/verify`, `/api/batch`, `/api/batch/{id}`,
`/api/history` (verify fully working via stubbed services; batch/history may be minimal
stubs refined in Phases 9–10), enforces upload validation and the standard error format, and
all endpoints are covered by `TestClient` tests with mocked services.

**Depends on:** Phase 5.

**Files to create/modify:**

- `backend/app/main.py`
- `backend/app/utils/validation.py` (upload validation + magic bytes)
- `backend/app/routers/verify.py`
- `backend/app/routers/batch.py`
- `backend/app/routers/history.py` (minimal — full impl in Phase 9)
- `backend/app/services/dependencies.py` (DI providers: `get_pipeline`, `get_ocr_service`, etc.)
- `backend/tests/conftest.py` (add `test_client`, `mock_ocr_service`, `mock_parser_service` fixtures)
- `backend/tests/test_api.py`

**Implementation steps:**

1. Create `app/utils/validation.py` with `validate_upload(file: UploadFile) -> bytes` (async): check `content_type in ALLOWED_IMAGE_TYPES` else raise `InvalidImageError`; read bytes, check size ≤ `MAX_IMAGE_SIZE_BYTES` else raise; validate magic bytes match declared type (JPEG `FF D8 FF`, PNG `89 50 4E 47`, PDF `25 50 44 46`) via a `_validate_magic_bytes(content, content_type) -> bool` helper; sanitize/reject filenames containing `..` or path separators (raise `InvalidImageError`); return the bytes (so the handler doesn't re-read). Follow security.rules → Input Validation.

2. Create `app/services/dependencies.py` with FastAPI dependency providers that pull pre-built singletons off `app.state` (set in lifespan): `get_pipeline(request) -> VerificationPipeline`, plus `get_db` (placeholder returning `None` until Phase 9; or a context-managed session once Phase 9 lands). Keep handlers thin per code-style.rules.

3. Create `app/main.py` per SPEC.md §2.2: `lifespan` validates config (`load_and_validate_config`), initializes DB (no-op until Phase 9 — call a `init_database` that's a stub now), builds `OCRService`, `GPTParser`, `Comparator`, and `VerificationPipeline`, stores them on `app.state`; shutdown calls `close()` on services. Add `CORSMiddleware` with `allow_origins=["http://localhost:5173", os.getenv("FRONTEND_URL", "http://localhost:5173")]`, `allow_methods=["GET","POST"]`, `allow_headers=["Content-Type"]` (security.rules → CORS). Register exception handlers that return the standard `{"error","detail"}` shape: `OCRExtractionError`→502, `ParserError`→502, `InvalidImageError`→400, and a global `Exception`→500 that logs server-side only (no stack trace to client). Include the three routers with prefix `/api`. Set `title="TTB Label Verification"`.

4. Create `app/routers/verify.py` implementing `POST /verify` per SPEC.md §4.1 handler pseudocode: accept `file: UploadFile`, `application_data: str = Form(...)`; `await validate_upload(file)`; `ApplicationData.model_validate_json(application_data)` (Pydantic ValidationError → FastAPI returns 422 automatically — ensure it surfaces as 422); call `pipeline.verify(...)`; (DB save wired in Phase 9 — leave a `# Phase 9: save_verification(...)` marker); return `VerificationResult`. `response_model=VerificationResult`.

5. Create `app/routers/batch.py` with `POST /batch` and `GET /batch/{batch_id}` returning `BatchStatus`. For Phase 6, implement a minimal **synchronous** version backed by an in-memory dict: validate file count ≤ `MAX_BATCH_SIZE` and that `application_data` (JSON array) length matches file count (else 400 with standard error), process each via the stubbed pipeline, store results in the in-memory store keyed by `bat_<uuid8>`, return 202 with initial status. `GET` returns the stored `BatchStatus` or 404. (Phase 10 replaces this with real async/semaphore processing.)

6. Create `app/routers/history.py` with `GET /history` returning `HistoryResponse`. Phase 6 stub: return `HistoryResponse(total=0, limit=limit, offset=offset, results=[])` reading `limit` (default 20, max 100), `offset` (default 0), `status` (optional) query params with validation. (Phase 9 wires it to SQLite.)

7. Expand `backend/tests/conftest.py` with fixtures from testing.rules → Mocking Strategy:
   - `test_client` — `TestClient(app)`.
   - `mock_ocr_service(mocker)` — `mocker.patch` `OCRService.extract_text` to return a fixed `OCRResult`.
   - `mock_parser_service(mocker)` — `mocker.patch` `GPTParser.extract_fields` to return a fixed `ExtractedFields`.
   - Helper to build a small valid in-memory PNG (use Pillow to generate a 1×1 PNG with correct magic bytes) and matching `application_data` JSON for multipart posts.

8. Create `backend/tests/test_api.py` covering testing.rules #16–#22:
   - `#16` verify happy path → 200, body has `fields`, `processing_time_ms >= 0`.
   - `#17` invalid file type (`.txt`) → 400 with `{"error","detail"}`.
   - `#18` missing `application_data` / malformed JSON → 422.
   - `#19` `POST /batch` with 3 files + matching data → 202 with `batch_id`.
   - `#20` `GET /batch/{id}` → existing returns status; nonexistent → 404.
   - `#21` `GET /history` → 200 with paginated shape (count/ordering assertions become meaningful after Phase 9; assert shape now).
   - `#22` path traversal: filename `../../etc/passwd` → 400.

**Verification:**

- `cd backend && pytest tests/test_api.py -v` passes (services mocked; no API keys).
- `cd backend && uvicorn app.main:app` boots (with dummy env vars set) and `GET /docs` renders all endpoints. (If real env vars are absent, lifespan should fail fast — that's correct; set dummy values to smoke-test boot.)
- `ruff check . && ruff format --check . && mypy app/` clean.

**Commit:** `feat(api): add FastAPI app, routers, upload validation, and endpoint tests`

---

## Phase 7: Azure AI Vision Integration (real OCR)

**Goal:** `OCRService.extract_text` makes a real Azure AI Vision Read call via `httpx`, parses
the response into `OCRResult`, and handles errors per SPEC.md §3.1 — with the stub path
removed but unit tests still passing offline via mocked HTTP.

**Depends on:** Phase 6.

**Files to modify/create:**

- `backend/app/services/ocr.py` (replace stub with real httpx call)
- `backend/tests/test_ocr.py` (unit test with `respx`-mocked HTTP + an `@pytest.mark.integration` real test)

**Implementation steps:**

1. In `OCRService.__init__`, create `self._client = httpx.AsyncClient(base_url=endpoint, headers={"Ocp-Apim-Subscription-Key": key}, timeout=timeout_seconds)` (security.rules → API Key Handling). Never store the key anywhere it could be logged.

2. Implement `extract_text` per SPEC.md §3.1 processing logic:
   - `POST /computervision/imageanalysis:analyze?api-version=2024-02-01&features=read` with `Content-Type: application/octet-stream` and the raw bytes as body.
   - `response.raise_for_status()` wrapped to translate errors: 4xx → `OCRExtractionError` with status context; 429 → `OCRExtractionError` mentioning rate limit; 5xx/timeout (`httpx.TimeoutException`) → `OCRExtractionError("Azure AI Vision unavailable")`.
   - Parse `readResult.blocks[].lines[]`: collect `.text`, `.words[].confidence`, `.boundingPolygon`. Join line texts with `\n` → `OCRResult.text`. `average_confidence` = mean of all word confidences (guard divide-by-zero → 0.0). If `average_confidence < 0.70` append `"low_confidence"` to `image_quality_issues`. Empty response → `OCRResult(text="", image_quality_issues=["no_text_detected"])`.

3. Implement `close()` to `await self._client.aclose()`.

4. **Logging** (code-style.rules + security.rules): log endpoint path, response status, latency — NEVER the key, NEVER the full OCR text.

5. `backend/tests/test_ocr.py`:
   - **Deterministic unit tests** with `respx` mocking the Azure endpoint: a successful response fixture → assert `OCRResult.text` joined correctly and `average_confidence` computed; a 401 → asserts `OCRExtractionError`; a 429 → `OCRExtractionError`; empty `readResult` → `no_text_detected` issue.
   - **Integration test** `@pytest.mark.integration test_ocr_real_azure` that `pytest.skip()`s if `AZURE_VISION_KEY`/`AZURE_VISION_ENDPOINT` are unset (per AGENTS.md), otherwise calls a real label image from `test_labels/` and asserts non-empty text.

6. Add a small synthetic `test_labels/bourbon_clean.png` if not present (Pillow-generated placeholder is fine for the prototype; mark with a comment that real labels replace it). Keep under 5MB (AGENTS.md).

**Verification:**

- `cd backend && pytest tests/test_ocr.py -v -m "not integration"` passes offline (respx-mocked).
- `cd backend && pytest tests/ -v -m "not integration"` — full deterministic suite still green.
- `ruff check . && ruff format --check . && mypy app/services/ocr.py` clean.

**Commit:** `feat(ocr): integrate Azure AI Vision Read API with httpx and error handling`

---

## Phase 8: GPT-4o Parser Integration (real)

**Goal:** `GPTParser.extract_fields` makes a real OpenAI Chat Completions call with the exact
prompt template, `temperature=0.0`, JSON mode, parses the response into `ExtractedFields`, and
handles errors — with deterministic parsing tests still passing offline.

**Depends on:** Phase 6 (uses Phase 5's `parse_gpt_extraction`).

**Files to modify:**

- `backend/app/services/parser.py` (replace stub `extract_fields` with real httpx call; keep `parse_gpt_extraction`)
- `backend/tests/test_parser.py` (add `respx`-mocked unit test + `@pytest.mark.integration` real test)
- `backend/app/utils/constants.py` (add the prompt template constants) OR a new `app/services/prompts.py`

**Implementation steps:**

1. Add the **exact** extraction system prompt (from prompts.rules → Field Extraction System Prompt) as a constant `FIELD_EXTRACTION_SYSTEM_PROMPT` in `app/utils/constants.py`:

   ```python
   FIELD_EXTRACTION_SYSTEM_PROMPT = """You are a label data extraction assistant for the TTB (Alcohol and Tobacco Tax and Trade Bureau).

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
   """

   FIELD_EXTRACTION_USER_TEMPLATE = (
       "Extract the label fields from the following OCR text:\n\n---\n{ocr_text}\n---"
   )
   ```

2. In `GPTParser.__init__`, create `self._client = httpx.AsyncClient(base_url="https://api.openai.com/v1", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, timeout=timeout_seconds)`.

3. Implement `extract_fields(ocr_text)` per SPEC.md §3.2 + prompts.rules:
   - Build the request body: `model="gpt-4o"`, `max_tokens=1000`, `temperature=0.0`, `response_format={"type":"json_object"}`, messages = system prompt + user message from the template.
   - `POST /chat/completions`; translate errors: 401 → `ParserError` (config error), 429 → `ParserError` with retry-after context, other 4xx/5xx → `ParserError` with status.
   - Pass the parsed response dict to `parse_gpt_extraction()` (the Phase 5 pure helper) to get `ExtractedFields`. Set `raw_ocr_text=ocr_text` on the result for debugging.
   - **Critical constraint (SPEC.md §3.2):** never send application data to GPT — only the OCR text. Log `usage.total_tokens` (count only, not content). Never log the prompt or response bodies (security.rules).

4. Implement `close()` → `await self._client.aclose()`.

5. `backend/tests/test_parser.py` additions:
   - **Deterministic** `respx`-mocked test: mock `POST https://api.openai.com/v1/chat/completions` to return `valid_extraction.json` → assert `extract_fields` yields populated `ExtractedFields`; mock a 429 → asserts `ParserError`; mock a body whose content is non-JSON → `ParserError`.
   - Keep the Phase 5 `parse_gpt_extraction` fixture tests (#10–#13).
   - **Integration** `@pytest.mark.integration test_parser_real_openai` — `pytest.skip()` without `OPENAI_API_KEY`; otherwise send a sample OCR string and assert `brand_name` extracted.

**Verification:**

- `cd backend && pytest tests/test_parser.py -v -m "not integration"` passes offline.
- `cd backend && pytest tests/ -v -m "not integration"` — full deterministic suite green.
- `grep -n "application_data\|expected" app/services/parser.py` confirms no application data path into the prompt.
- `ruff check . && ruff format --check . && mypy app/services/parser.py` clean.

**Commit:** `feat(parser): integrate GPT-4o field extraction with exact prompt template`

---

## Phase 9: SQLite Database + History Endpoint

**Goal:** Verification results persist to SQLite via SQLAlchemy, `/api/verify` saves each
result, and `/api/history` returns real paginated, status-filtered results in reverse
chronological order.

**Depends on:** Phase 6 (and benefits from 7/8, but works with stubs too).

**Files to create/modify:**

- `backend/app/models/database.py`
- `backend/app/services/persistence.py` (save + query helpers)
- `backend/app/routers/verify.py` (wire `save_verification`)
- `backend/app/routers/history.py` (real query)
- `backend/app/main.py` (`init_database` real impl in lifespan; `get_db` dependency)
- `backend/app/services/dependencies.py` (`get_db` session provider)
- `backend/tests/test_history.py` (and extend `test_api.py` #21)

**Implementation steps:**

1. Create `app/models/database.py` per prompts.rules → Database Model: `Base = declarative_base()`, `VerificationRecord` with columns `id` (PK), `timestamp`, `status`, `processing_time_ms`, `application_data` (JSON), `field_results` (JSON), `image_quality` (JSON), `batch_id` (nullable). Add `create_engine`, `sessionmaker` (`SessionLocal`), and `init_database(database_url) -> None` that creates the engine, calls `Base.metadata.create_all(engine)`, and creates the three indexes from SPEC.md §6 (timestamp DESC, status, batch_id) — SQLAlchemy `Index` definitions on the model. Store the engine/sessionmaker module-level or on app state.

2. Create `app/services/persistence.py`:
   - `save_verification(db, result: VerificationResult, app_data: ApplicationData, batch_id: str | None = None) -> None` — maps the Pydantic result to a `VerificationRecord` (JSON-dump `application_data`, `field_results`, `image_quality`) and commits. Per security.rules: **do not store raw OCR text, GPT responses, or images** — only the comparison results and metadata.
   - `query_history(db, limit: int, offset: int, status: str | None) -> tuple[int, list[VerificationResult]]` — returns total count (with filter) and the page, ordered `timestamp DESC`, reconstructing `VerificationResult` objects from the stored JSON.

3. In `app/main.py` lifespan, call the real `init_database(config.database_url)`. Add `get_db` in `dependencies.py` yielding a `SessionLocal()` and closing it in `finally`.

4. Wire `save_verification` into `verify.py` (replace the Phase 6 marker). The handler now depends on `db: Session = Depends(get_db)`.

5. Implement `history.py` real query: validate `limit` (default 20, clamp/validate max 100 → 422 if exceeded or use `Query(20, le=100)`), `offset` (default 0, ≥0), optional `status` filter validated against `{"PASS","REVIEW_NEEDED","FAIL"}`. Return `HistoryResponse`.

6. Tests:
   - `backend/tests/test_history.py`: use a temp SQLite DB (tmp_path or in-memory). Insert several `VerificationRecord`s with mixed statuses/timestamps. Assert: default pagination returns ≤20 newest-first; `status` filter narrows correctly; `offset` paginates; `total` reflects filtered count. (testing.rules #21.)
   - Update `test_api.py` #21 to post a verify (mocked services), then GET `/history` and assert the just-saved record appears.
   - Use a fixture that points `DATABASE_URL` at a temp file and re-inits the DB per test to keep tests isolated.

**Verification:**

- `cd backend && pytest tests/test_history.py tests/test_api.py -v -m "not integration"` passes.
- A manual `POST /api/verify` (stub services) followed by `GET /api/history` returns the record.
- No `.db` file is committed (gitignored).
- `ruff check . && ruff format --check . && mypy app/` clean.

**Commit:** `feat(models): add SQLite persistence and paginated history endpoint`

---

## Phase 10: Batch Processing

**Goal:** `/api/batch` accepts up to `MAX_BATCH_SIZE` files with per-file application data,
processes them asynchronously with a concurrency semaphore, records each result (with
`batch_id`) to SQLite, and `/api/batch/{id}` reports live progress then final results.

**Depends on:** Phase 9.

**Files to modify/create:**

- `backend/app/routers/batch.py` (real async implementation)
- `backend/app/services/batch_store.py` (in-memory batch progress registry)
- `backend/tests/test_batch.py`

**Implementation steps:**

1. Create `app/services/batch_store.py`: an in-memory registry (module-level dict guarded by an `asyncio.Lock`) mapping `batch_id → BatchStatus` plus accumulating results. Functions: `create_batch(total) -> str` (returns `bat_<uuid8>`), `update_batch_progress(batch_id, completed)`, `append_result(batch_id, result)`, `finalize_batch(batch_id)` (sets status `complete`), `get_batch(batch_id) -> BatchStatus | None`, `fail_batch(batch_id)`. (Note: in-memory state is per-process — acceptable for the prototype; production uses a job queue per README Known Limitations.)

2. Rewrite `POST /batch` per SPEC.md §4.2:
   - Parse `files: list[UploadFile]` and `application_data: str = Form(...)` (a JSON array). Validate: `len(files) <= MAX_BATCH_SIZE` (else 400 "Maximum 50 labels per batch."), `len(files) == len(app_data_array)` (else 400 with the count-mismatch message from SPEC.md §8), each file passes `validate_upload`, each array entry validates as `ApplicationData`.
   - `create_batch(total=len(files))`, return **202** with the initial `BatchStatus`.
   - Kick off background processing via FastAPI `BackgroundTasks` (or `asyncio.create_task`). Background coroutine mirrors SPEC.md §4.2 `process_batch`: `semaphore = asyncio.Semaphore(config.ocr_concurrency_limit)`, `process_one` acquires the semaphore, runs `pipeline.verify`, appends result, calls `save_verification(..., batch_id=batch_id)`, updates progress; `await asyncio.gather(*...)`; then `finalize_batch`. Catch per-item errors so one failure doesn't sink the batch (record a FAIL result or skip+log) and `fail_batch` only on catastrophic errors.

3. Rewrite `GET /batch/{batch_id}`: return `get_batch(...)` (status `processing` with `results=None`, or `complete` with `results=[...]`); 404 if unknown.

4. `backend/tests/test_batch.py` (testing.rules #19, #20, plus concurrency): with mocked services —
   - Submit 3 files + 3-entry data array → 202 with `batch_id`.
   - Poll `GET /batch/{id}` until `complete`; assert `total==3`, `completed==3`, `len(results)==3`.
   - File/data count mismatch → 400.
   - Exceeding `MAX_BATCH_SIZE` → 400.
   - Unknown batch id → 404.
   - Use `TestClient` (it runs the event loop and background tasks); if background tasks need awaiting, poll within the test with a short bounded loop.

**Verification:**

- `cd backend && pytest tests/test_batch.py -v -m "not integration"` passes (mocked services).
- Full deterministic suite `pytest tests/ -v -m "not integration"` green.
- `ruff check . && ruff format --check . && mypy app/` clean.

**Commit:** `feat(api): add async batch upload with concurrency limit and progress polling`

---

## Phase 11: React Frontend

**Goal:** A Vite + React + Tailwind app implements the single-verification, batch, and history
views per SPEC.md §5, talks to the working backend, and meets the accessibility/usability bars
from PRD §3.2 (NFR-2).

**Depends on:** Phase 6 (single verify) at minimum; ideally Phases 9–10 for history/batch.

**Files to create:**

- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/vite.config.js`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`
- `frontend/index.html`
- `frontend/src/main.jsx`, `frontend/src/App.jsx`, `frontend/src/index.css`
- `frontend/src/api.js` (fetch wrappers)
- `frontend/src/components/UploadZone.jsx`
- `frontend/src/components/ApplicationForm.jsx`
- `frontend/src/components/FormField.jsx`
- `frontend/src/components/ResultsPanel.jsx`
- `frontend/src/components/FieldResult.jsx`
- `frontend/src/components/StatusBadge.jsx`
- `frontend/src/components/BatchUpload.jsx`
- `frontend/src/components/BatchResults.jsx`
- `frontend/src/components/History.jsx`
- `frontend/.eslintrc` / `eslint.config.js`, `.prettierrc`

**Implementation steps:**

1. Scaffold Vite React app (`npm create vite@latest . -- --template react`), add Tailwind (`tailwindcss`, `postcss`, `autoprefixer`), configure `tailwind.config.js` `content` globs and **semantic verdict colors** (`match`/`mismatch`/`warning`/`not-found`) per code-style.rules → Styling. Add ESLint + Prettier configs. Pin deps in `package.json`; commit `package-lock.json`.

2. `src/api.js`: implement `verifyLabel(imageFile, applicationData)` and `pollBatchStatus(batchId, onProgress)` exactly per SPEC.md §5.4 (FormData, `fetch`, `response.ok` check, error JSON parsing, 1s polling). Add `submitBatch(files, applicationDataList)` and `fetchHistory({limit, offset, status})`. Base URL from `import.meta.env.VITE_API_URL`. Use `AbortController` for cancellable uploads (code-style.rules → API Communication).

3. App-level state in `App.jsx` per SPEC.md §5.3 (`view`, `single`, `batch`, `history` substates) using `useState`/`useReducer`. Header with nav: Single | Batch | History.

4. `UploadZone.jsx` per SPEC.md §5.2: drag-and-drop with dashed border, icon, "Drop label image here", fallback browse button, client-side type validation (`.jpg/.jpeg/.png/.pdf`), image preview, dragover visual feedback, ≥200×150px target. Fallback `<input type="file">` (accessibility).

5. `ApplicationForm.jsx` + `FormField.jsx`: seven labeled fields; required (brand_name, class_type, abv, net_contents, warning_statement) marked with `*`; optional (producer, origin) labeled optional; warning_statement is a 4-row `<textarea>`; submit validation highlights missing required fields; "Pre-fill sample data" button using the bourbon sample. Every input has an associated `<label>` (accessibility).

6. `ResultsPanel.jsx` + `FieldResult.jsx` + `StatusBadge.jsx` per SPEC.md §5.2: overall status banner (green PASS / yellow REVIEW_NEEDED / red FAIL); per-field rows with name, `StatusBadge` (color **and** icon **and** text), extracted value, expected value, similarity (when present), note; MISMATCH rows visually prominent; processing time footer "Verified in N.N seconds". Move focus to the results panel on completion (accessibility).

7. `BatchUpload.jsx` + `BatchResults.jsx` per SPEC.md §5 and PRD Flow 2: multi-file upload (≤50), file list, JSON data upload or per-file entry, progress bar ("Processing X of N labels…"), summary table with pass/review/fail counts, status filter (All / Mismatches / Warnings), expandable rows → reuse `ResultsPanel`.

8. `History.jsx`: status filter, paginated table (20/page) reverse-chronological, expandable rows → `ResultsPanel`.

9. Usability/accessibility bar (PRD NFR-2 + code-style.rules → Accessibility): body text ≥16px, interactive targets ≥44×44px, color + text/icon for all statuses, no hidden menus/tooltips for core flow, plain-English errors, ≤3 steps for single verification.

**Verification:**

- `cd frontend && npm install && npm run build` succeeds (no type/lint errors blocking build).
- `cd frontend && npx eslint src/ && npx prettier --check src/` clean.
- With the backend running (stub or real env), `npm run dev` → upload a label + sample data → results render with per-field badges; batch and history tabs load.

**Commit:** `feat(frontend): add React UI for single, batch, and history verification flows`

---

## Phase 12: Docker + Deployment Config

**Goal:** A multi-stage Dockerfile builds the frontend and serves it as static assets from the
FastAPI container running as a non-root user; deployment notes document the Azure App Service
path.

**Depends on:** Phase 11.

**Files to create/modify:**

- `Dockerfile` (repo root)
- `.dockerignore` (repo root)
- `backend/app/main.py` (mount static frontend assets when present)
- `docs/architecture-decisions.md` (deployment notes; create if absent)
- `README.md` (confirm Docker/deploy commands match)

**Implementation steps:**

1. Create the multi-stage `Dockerfile` from SPEC.md §9.1 / security.rules → Docker Security: Stage 1 `node:20-alpine` builds the frontend (`npm ci`, `npm run build`); Stage 2 `python:3.11-slim` creates a non-root `appuser`, installs `backend/requirements.txt`, copies `backend/`, copies `--from=frontend /app/frontend/dist ./static`, sets `PYTHONDONTWRITEBYTECODE=1` / `PYTHONUNBUFFERED=1`, `USER appuser`, `EXPOSE 8000`, `CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]`. Use pinned tags, never `latest`. Do NOT copy `.env`.

2. Create `.dockerignore` excluding `node_modules`, `__pycache__`, `.pytest_cache`, `venv`, `.venv`, `*.db`, `.env`, `.env.*`, `frontend/dist`, `.git`, `tests` (optional), so the build context is minimal and secret-free.

3. In `app/main.py`, after routers, mount static assets if the `static/` directory exists: `app.mount("/", StaticFiles(directory="static", html=True), name="static")` guarded by a path-exists check (so dev backend without a build still runs). Ensure `/api/*` routes are registered before the catch-all mount.

4. Create/expand `docs/architecture-decisions.md` with: the Azure App Service deployment commands from SPEC.md §9.2 (`az acr build`, `az webapp create`, `az webapp config appsettings set`), a note that env vars are set via App Service settings (never baked into the image), and a short recap of the key design decisions (two-step pipeline, deterministic comparison engine, SQLite audit trail) cross-referencing README.

5. Verify README Quick Start / Docker commands match the actual Dockerfile (`docker build -t ttb-verify .`, `docker run -p 8000:8000 --env-file backend/.env ttb-verify`).

**Verification:**

- `docker build -t ttb-verify .` succeeds.
- `docker run -p 8000:8000 --env-file backend/.env ttb-verify` boots; `GET http://localhost:8000/docs` works and the frontend is served at `/`.
- `docker run` confirms the process runs as `appuser` (`docker exec ... whoami` → `appuser`).
- No `.env` or secrets present in the image (`docker history` / inspect the build context via `.dockerignore`).

**Commit:** `chore(docker): add multi-stage Dockerfile and Azure deployment notes`

---

## Cross-cutting reminders for every phase

- **Run `ruff format .` and `ruff check .` before every commit; fix all warnings.** (code-style.rules)
- **Run the relevant `pytest` (deterministic, `-m "not integration"`) before every commit; never commit failing tests.** (AGENTS.md)
- **Never commit** `.env`, API keys, `__pycache__/`, `.pytest_cache/`, `node_modules/`, `*.db`, or test images >5MB. Run the security.rules secret-scan grep before committing.
- **Conventional Commits** with the scopes from AGENTS.md (`ocr`, `parser`, `comparator`, `api`, `models`, `frontend`, `docker`, `docs`, `tests`).
- **The comparison engine boundary is sacred** — no I/O, no API calls in `comparator.py`, ever.
- **Integration tests** (`@pytest.mark.integration`) must `pytest.skip()` when their API keys are absent.
- Each phase must leave the project in a **working, non-broken state**.
