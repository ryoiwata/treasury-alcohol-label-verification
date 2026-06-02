# Code Style Rules

## Python (Backend)

### General
- Python 3.11+ features are fine (StrEnum, ExceptionGroup, tomllib, etc.)
- All public functions and classes get docstrings. Skip for obvious private helpers.
- Use explicit return types on all function signatures.
- Prefer raising specific exceptions over returning None silently.
- Use `typing` annotations everywhere — no untyped function signatures.

### Formatting
- `ruff format` is the standard. No exceptions.
- `ruff check` for linting. Fix all warnings before committing.
- Imports: stdlib → third-party → local, separated by blank lines. `ruff` handles this via `isort` rules.
- Line length: 88 characters (ruff default). Break long function signatures for readability.

### Naming
- `snake_case` for functions, variables, modules.
- `PascalCase` for classes, Pydantic models, enums.
- `UPPER_SNAKE_CASE` for constants and environment variable names.
- Acronyms in class names stay consistent case: `OCRService`, `ABVExtractor`, `GPTParser` (not `OcrService`, `AbvExtractor`).
- Module names are short, singular, lowercase: `ocr`, `parser`, `comparator`, `normalization`.
- Pydantic models describe their purpose: `VerificationResult`, `FieldComparison`, `ApplicationData` — not `DataModel1`.

### Error Handling
- Always raise specific exceptions with context: `raise ValueError(f"Invalid ABV format: {raw_value!r}")`.
- Never swallow exceptions silently. If you catch it, log it or re-raise with context.
- Use custom exception classes for domain errors:
  ```python
  class OCRExtractionError(Exception): ...
  class ParserError(Exception): ...
  class InvalidImageError(ValueError): ...
  ```
- Return early on validation failures — no deep nesting.
- Use `try/except` narrowly — catch the specific exception, not bare `Exception`.

### Pydantic Models
- All API request/response types are Pydantic `BaseModel` subclasses. No raw dicts at API boundaries.
- Use `Field()` with descriptions for API-facing models — these appear in OpenAPI docs.
- Use `model_validator` for cross-field validation (e.g., ABV range checks).
- Use `Literal` types for enum-like string fields: `status: Literal["MATCH", "MISMATCH", "WARNING", "NOT_FOUND"]`.
- Never use `dict[str, Any]` — define the shape explicitly.

### HTTP Client (Azure & OpenAI APIs)
- Use `httpx` for async HTTP calls. No `requests` library (it's synchronous).
- Set explicit timeouts: `httpx.AsyncClient(timeout=30.0)` for OCR, `timeout=60.0` for GPT.
- Check response status explicitly: `response.raise_for_status()`.
- All request/response types are Pydantic models with `json` aliases where API field names differ.
- Use `async with httpx.AsyncClient() as client:` for proper connection cleanup.

### FastAPI Server
- Route handlers are thin: parse request, call service, return response. No business logic in handlers.
- Use dependency injection for services: `ocr_service: OCRService = Depends(get_ocr_service)`.
- Use `APIRouter` for route grouping with prefixes: `/api/verify`, `/api/batch`, `/api/history`.
- Return Pydantic models from handlers — FastAPI serializes them automatically.
- Use proper HTTP status codes: 400 for bad input, 404 for not found, 500 for internal errors, 202 for accepted (batch).
- Use `UploadFile` for file uploads. Validate file type and size before processing.

### Async
- Use `async def` for all route handlers and service methods that do I/O.
- Use `asyncio.gather()` for parallel processing in batch uploads (with concurrency limit).
- Use `asyncio.Semaphore` to limit concurrent API calls (default: 5 for OCR, 3 for GPT).
- Never mix sync and async I/O in the same call chain — use `run_in_executor` for sync libraries if needed.

### Logging
- Use Python `logging` module with structured output.
- JSON format in production, text format in dev (controlled by `LOG_LEVEL` env var).
- Log: verification start/complete, API call durations, comparison results summary, batch progress.
- **Never log:** API keys, full GPT request/response bodies, raw image data.
- Use structured fields: `logger.info("verification complete", extra={"verification_id": vid, "processing_ms": elapsed, "field_count": len(results)})`.

### Project-Specific
- **The comparison engine (`app/services/comparator.py`) is pure Python with zero API calls.** This boundary is sacred.
- **Warning statement matching is always exact** (after whitespace normalization). Never use fuzzy matching for warnings.
- **ABV comparison extracts numeric values** before comparing. "45% Alc./Vol. (90 Proof)" → 45.0.
- **Fuzzy match thresholds are configurable** via environment variables, not hardcoded magic numbers.
- **Government warning text is a constant** in `app/utils/constants.py`, not embedded in comparison logic.
- **File uploads are validated** for type (JPEG, PNG, PDF) and size (max 10MB) before processing.

## TypeScript / React (Frontend)

### General
- TypeScript strict mode. No `any` — use `unknown` and narrow.
- Functional components with hooks only. No class components.
- Use named exports, not default exports (except for `App.tsx`).
- `.jsx` extension for components, `.ts` for non-component modules.

### Formatting
- Prettier via Vite plugin. No debate.
- Imports: react → third-party → local components → local utils → types.

### Naming
- `PascalCase` for components and types: `UploadZone`, `ResultsPanel`, `FieldResult`.
- `camelCase` for functions, variables, hooks: `useVerification`, `handleUpload`, `fieldResult`.
- File names match component names: `UploadZone.jsx`, `ResultsPanel.jsx`.

### Styling
- Tailwind utility classes. No custom CSS files except for global resets.
- Avoid inline styles. If Tailwind doesn't cover it, use a `<style>` block in the component file.
- Use semantic color names via Tailwind config for verdict statuses: `bg-match`, `bg-mismatch`, `bg-warning`.

### State Management
- React state (`useState`, `useReducer`) only. No external state library for a prototype.
- Lift state to the nearest common ancestor. App-level state in `App.jsx`.
- Use `useRef` for file input elements and abort controllers.

### API Communication
- Use `fetch` for REST calls to the FastAPI backend. No axios.
- Handle errors explicitly: check `response.ok`, parse error JSON, display to user.
- Use `AbortController` for cancellable uploads.
- Show loading states during API calls — never freeze the UI.

### Components
- `UploadZone`: drag-and-drop image upload. Accepts JPEG, PNG, PDF. Shows preview.
- `ApplicationForm`: labeled input fields for application data (brand name, ABV, class/type, etc.).
- `ResultsPanel`: verification results container with overall status banner.
- `FieldResult`: individual field verdict row — extracted value, expected value, status badge, similarity score.
- `BatchUpload`: multi-file upload with progress indicator per file.
- `BatchResults`: summary table with per-label drill-down.

### Accessibility
- All form inputs have associated `<label>` elements.
- Status badges use both color AND text/icon (not color alone — colorblind users).
- Drag-and-drop zone has a fallback file input button.
- Focus management: after upload completes, focus moves to results panel.
- Font sizes minimum 16px for body text (agents over 50 are a primary user group).

## Makefile

Standard targets:
```makefile
install:         cd backend && pip install -r requirements.txt && cd ../frontend && npm install
dev-backend:     cd backend && uvicorn app.main:app --reload
dev-frontend:    cd frontend && npm run dev
test:            cd backend && pytest tests/ -v -m "not integration"
test-integration: cd backend && pytest tests/ -v -m integration
lint:            cd backend && ruff check . && cd ../frontend && npx eslint src/
fmt:             cd backend && ruff format . && cd ../frontend && npx prettier --write src/
docker:          docker build -t ttb-verify .
run:             docker run -p 8000:8000 --env-file backend/.env ttb-verify
clean:           rm -rf backend/__pycache__ backend/.pytest_cache frontend/node_modules/.vite
```
