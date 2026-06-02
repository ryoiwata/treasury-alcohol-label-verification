# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and Codex when working with code in this repository.

## Project Overview

TTB Label Verification is a prototype AI-powered tool that automates alcohol beverage label compliance checks for the Treasury Department's Alcohol and Tobacco Tax and Trade Bureau (TTB). It extracts text from label images using Azure AI Vision, structures the data with GPT-4o, and programmatically verifies each field against application data — reducing a 5–10 minute manual review to under 5 seconds.

**Stack:** Python 3.11 · FastAPI · Azure AI Vision · OpenAI GPT-4o · SQLite · React (Vite) · Tailwind · Docker

**Do not suggest switching frameworks or languages.** The stack mirrors Treasury's Azure infrastructure (Python for AI/ML, React frontend, Azure services) and is intentional.

## Commands

### Build & Run

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # Add API keys
uvicorn app.main:app --reload     # Dev server at http://localhost:8000

# Frontend
cd frontend
npm install
cp .env.example .env              # Set VITE_API_URL
npm run dev                       # Dev server at http://localhost:5173
```

### Testing

```bash
cd backend
pytest tests/ -v                                  # All unit tests (no API keys needed)
pytest tests/test_comparator.py -v                # Comparison engine only
pytest tests/test_normalization.py -v             # Text normalization only
pytest tests/test_api.py -v                       # API endpoint tests
pytest tests/ -m integration -v                   # Integration tests (needs API keys)
pytest tests/ -m "not integration" -v             # Deterministic tests only
```

### Linting & Formatting

```bash
cd backend
ruff check .                      # Lint
ruff format .                     # Format
mypy app/                         # Type check

cd frontend
npx eslint src/                   # Lint
npx prettier --write src/         # Format
```

### Docker

```bash
docker build -t ttb-verify .
docker run -p 8000:8000 --env-file backend/.env ttb-verify
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_VISION_ENDPOINT` | Yes | — | Azure AI Vision endpoint URL |
| `AZURE_VISION_KEY` | Yes | — | Azure AI Vision API key |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for GPT-4o |
| `DATABASE_URL` | No | `sqlite:///./verification.db` | SQLite database path |
| `LOG_LEVEL` | No | `info` | Logging level (debug, info, warning, error) |
| `MAX_BATCH_SIZE` | No | `50` | Maximum labels per batch upload |
| `MATCH_THRESHOLD` | No | `0.95` | Fuzzy match threshold for MATCH verdict |
| `WARNING_THRESHOLD` | No | `0.85` | Fuzzy match threshold for WARNING verdict |

## Project Structure

```
ttb-label-verification/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan, DB init
│   │   ├── routers/
│   │   │   ├── verify.py        # POST /api/verify — single label
│   │   │   ├── batch.py         # POST /api/batch, GET /api/batch/{id}
│   │   │   └── history.py       # GET /api/history — past results
│   │   ├── services/
│   │   │   ├── ocr.py           # Azure AI Vision integration
│   │   │   ├── parser.py        # GPT-4o field extraction
│   │   │   └── comparator.py    # Field-by-field comparison engine
│   │   ├── models/
│   │   │   ├── schemas.py       # Pydantic request/response models
│   │   │   └── database.py      # SQLAlchemy models + SQLite setup
│   │   └── utils/
│   │       ├── normalization.py # Text cleaning and normalization
│   │       └── constants.py     # Warning text, field configs, thresholds
│   ├── tests/
│   │   ├── conftest.py          # Shared fixtures (test client, mock services)
│   │   ├── test_comparator.py   # Comparison logic unit tests
│   │   ├── test_normalization.py
│   │   ├── test_parser.py       # GPT response parsing tests
│   │   ├── test_api.py          # Endpoint integration tests
│   │   └── fixtures/            # Mock OCR output, sample application data
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── ApplicationForm.jsx
│   │   │   ├── ResultsPanel.jsx
│   │   │   ├── FieldResult.jsx
│   │   │   ├── BatchUpload.jsx
│   │   │   └── BatchResults.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── .env.example
├── test_labels/                 # Sample label images for testing
├── docs/
│   └── architecture-decisions.md
├── Dockerfile
└── README.md
```

## Architecture — Three-Layer Pipeline

```
Label Image → Azure AI Vision (OCR) → GPT-4o (structuring) → Comparison Engine → Result
```

**Layer 1 — OCR extraction (`app/services/ocr.py`):**
Send the label image to Azure AI Vision. Receive raw extracted text with bounding box data. This is a deterministic API call — same image, same text. Azure-native, FedRAMP-authorized.

**Layer 2 — Field structuring (`app/services/parser.py`):**
Send the raw OCR text to GPT-4o with a structured extraction prompt. Receive JSON with labeled fields (brand_name, abv, warning_statement, etc.). This is where the LLM handles the unstructured-to-structured parsing that rule-based approaches can't — label layouts vary wildly.

**Layer 3 — Comparison engine (`app/services/comparator.py`):**
Pure Python, zero API calls. Compare each extracted field against application data using field-specific strategies. This layer is fully deterministic, fully testable, and must stay that way.

### Comparison Strategies by Field

| Field | Strategy | Rationale |
|-------|----------|-----------|
| `warning_statement` | Exact match after whitespace normalization | Must be word-for-word per TTB regulations |
| `abv` | Numeric extraction + tolerance check | "45% Alc./Vol." vs "45" — extract the number |
| `brand_name` | Fuzzy match (Levenshtein ratio) | Handle case, punctuation, OCR errors |
| `class_type` | Normalized string comparison | Standardize spacing and case |
| `net_contents` | Numeric extraction + unit normalization | "750 mL" vs "750ml" |
| `producer` | Fuzzy match | Address formatting varies |
| `origin` | Normalized string comparison | Country name standardization |

## Key Design Decisions

- **Two-step AI pipeline** — Azure Vision for OCR, GPT-4o for structuring. OCR stays on Azure network (FedRAMP). GPT receives only extracted text, never images, reducing data exposure.
- **Deterministic comparison engine** — All field matching is Python code, not LLM-based. Testable, auditable, explainable. Critical for government compliance where decisions may be challenged.
- **Three verdict levels** — MATCH, WARNING, MISMATCH. WARNING exists for cases needing human judgment (e.g., "STONE'S THROW" vs "Stone's Throw"). The tool assists agents, it does not replace them.
- **SQLite audit trail** — Every verification result is logged with timestamps and full extraction/comparison records. Zero-infrastructure persistence appropriate for a prototype.
- **Separate frontend and backend** — API-first design. FastAPI auto-generates OpenAPI docs. Backend could serve web UI, COLA integration, or reporting tools.

## Testing

- **Framework:** pytest with fixtures in `conftest.py`
- **Pattern:** Parametrized tests for comparison engine and normalization
- **Deterministic tests** (no API key): comparator logic, normalization, Pydantic schema validation, API endpoint wiring
- **Integration tests** (needs API keys): full pipeline end-to-end, OCR accuracy, GPT field extraction
- **Mark integration tests** with `@pytest.mark.integration` — they require API keys and are skipped in CI
- **The comparison engine is the most critical test target** — it contains all the business logic
- **Run deterministic tests on every commit. Integration tests before PR.**

## Git Workflow

### Conventional Commits

```
<type>(<scope>): <description>
```

**Types:** feat, fix, test, docs, refactor, chore, perf

**Scopes:** ocr, parser, comparator, api, models, frontend, docker, docs, tests

**Rules:**
- Lowercase type and description. No period at end.
- Imperative mood: "add", "fix", "update" — not "added", "fixes", "updated".
- Keep the first line under 72 characters.

**Examples:**
```
feat(comparator): add fuzzy matching for brand name with Levenshtein ratio
feat(ocr): integrate Azure AI Vision for label text extraction
feat(api): add batch upload endpoint with async processing
test(comparator): add parametrized tests for warning statement exact match
fix(parser): handle GPT responses missing optional fields gracefully
chore(docker): add multi-stage Dockerfile with Python + React builds
docs: update README with architecture decisions
```

### Auto-Commit Behavior

**After every meaningful change, the agent MUST `git add` all relevant files and `git commit` with a conventional commit message.** Do not wait for the user to ask.

**Commit workflow:**
1. Complete the logical unit of work
2. Run `ruff check .` and `ruff format .` — fix any issues before committing
3. Run relevant tests (`pytest tests/test_<module>.py -v`) — do not commit failing tests
4. `git add` all changed files related to this unit of work
5. `git commit -m "<type>(<scope>): <description>"`

**Do NOT commit:**
- `.env` files or API keys
- `__pycache__/`, `.pytest_cache/`, `node_modules/`
- Raw test label images over 5MB
- Failing tests or code that doesn't pass lint
- Unrelated changes bundled into one commit

## Rules

- Read `README.md` before starting any work — it contains the full architecture, API contracts, and design rationale
- **The comparison engine (`app/services/comparator.py`) is pure Python with zero API calls.** This boundary is sacred. Do not add LLM calls to comparison logic.
- Use Pydantic models for all request/response types — no raw dicts at API boundaries
- Use `typing` annotations on all function signatures
- Wrap errors with context: raise specific exceptions, not bare `Exception`
- Warning statement comparison must be exact match after whitespace normalization — never fuzzy
- ABV comparison must extract numeric values before comparing — "45% Alc./Vol." and "45" are the same
- Fuzzy match thresholds are configurable via environment variables, not hardcoded
- All API endpoints return JSON with consistent error format: `{"error": "message", "detail": "context"}`
- Never log API keys. Log that they are set or missing, not their values.
- Fail fast on startup if required environment variables are missing
- Test the comparison engine with parametrized tests covering: exact matches, near-misses, case differences, OCR artifacts, empty fields, special characters
- Integration tests must check for API key env vars and `pytest.skip()` if missing
- Keep CLAUDE.md under 50 instructions — put details in supporting docs
- Reference `docs/code-style.md` for language-specific formatting rules
- Reference `docs/testing.md` for test case requirements and mocking strategy
- Reference `docs/security.md` for secrets management and input validation rules
- Reference `docs/prompts.md` for API contracts, Pydantic schemas, and LLM prompt templates
