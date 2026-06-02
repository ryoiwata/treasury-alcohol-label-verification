# Security Rules

## Secrets Management

- **Never hardcode API keys.** `AZURE_VISION_KEY`, `AZURE_VISION_ENDPOINT`, and `OPENAI_API_KEY` come from environment variables only.
- Load secrets via `.env` file locally (gitignored). In Docker, use `--env-file` or `-e` flags.
- Required env vars: `AZURE_VISION_ENDPOINT`, `AZURE_VISION_KEY`, `OPENAI_API_KEY`.
- Never log API key values. Log only that the variable "is set" or "is missing".
- Fail fast on startup if any required env var is empty — don't let the user discover this mid-verification.

```python
# CORRECT: Read from environment, validate on startup
import os

def get_required_env(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value

AZURE_VISION_KEY = get_required_env("AZURE_VISION_KEY")

# CORRECT: Log presence, not value
logger.info("Azure Vision client initialized", extra={"key_set": bool(AZURE_VISION_KEY)})

# WRONG: Log the key
logger.info(f"Using key: {AZURE_VISION_KEY}")  # NEVER DO THIS

# WRONG: Include in error messages
raise RuntimeError(f"API call failed with key {api_key}")  # NEVER DO THIS
```

## .gitignore

The following must always be gitignored:
```
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

Note: `test_labels/` sample images ARE committed (small PNGs/JPEGs for testing). Raw high-resolution TIFFs are NOT (too large for git).

## Input Validation

### Image Uploads

- Validate MIME type before processing: accept only `image/jpeg`, `image/png`, `application/pdf`.
- Reject files larger than 10MB to prevent resource exhaustion.
- Validate file content matches declared MIME type (check magic bytes, don't trust `Content-Type` header alone).
- Store uploaded files in a temp directory with unique names. Clean up after verification completes or on error.
- Guard against path traversal: reject any filename containing `..` or absolute paths.
- Sanitize filenames before any filesystem operation.

```python
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

async def validate_upload(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise InvalidImageError(f"Unsupported file type: {file.content_type}")
    
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise InvalidImageError(f"File too large: {len(content)} bytes (max {MAX_FILE_SIZE})")
    
    # Reset file position after reading
    await file.seek(0)
    
    # Validate magic bytes match declared type
    if not _validate_magic_bytes(content, file.content_type):
        raise InvalidImageError("File content does not match declared type")
```

### Application Data

- Validate all required fields are present via Pydantic models.
- Strip HTML/script tags from text inputs.
- Set reasonable max length on string fields (default: 1000 characters for most fields, 2000 for warning statement).
- ABV must be a valid number between 0 and 100.
- Reject requests with unexpected fields (Pydantic `model_config = ConfigDict(extra="forbid")`).

### Batch Uploads

- Enforce maximum batch size (default: 50 files) to prevent resource exhaustion.
- Validate each file individually before starting batch processing.
- Rate limit batch submissions per session (max 5 concurrent batches).

## API Key Handling in Code

```python
# CORRECT: Pass as parameter, never as global
class OCRService:
    def __init__(self, endpoint: str, key: str):
        self._endpoint = endpoint
        self._key = key
        self._client = httpx.AsyncClient(
            base_url=endpoint,
            headers={"Ocp-Apim-Subscription-Key": key},
            timeout=30.0,
        )

# CORRECT: Dependency injection
def get_ocr_service() -> OCRService:
    return OCRService(
        endpoint=get_required_env("AZURE_VISION_ENDPOINT"),
        key=get_required_env("AZURE_VISION_KEY"),
    )

# WRONG: Global API key access
import app.config
headers = {"key": app.config.AZURE_VISION_KEY}  # Avoid module-level secrets
```

## Data Handling

### What Not to Log
- **Never log:** API keys, full GPT request/response bodies, raw image data (base64), full OCR output text.
- **Safe to log:** verification IDs, processing durations, field match statuses, confidence scores, file sizes, batch progress counts.
- When logging API interactions, log: endpoint URL, response status code, latency, token count (for GPT). Not the content.

### What Not to Send to GPT Unnecessarily
- Send only the OCR-extracted text to GPT, never the raw image.
- Include only the extraction prompt and OCR text — no application data goes to GPT (comparison happens locally).
- Keep prompts minimal: the system prompt describes the task, the user message contains only the OCR text.

### Database (SQLite)
- SQLite is for audit trail only. Do not store API keys or raw images in the database.
- Store: verification ID, timestamp, field comparison results, processing time, overall status.
- Do not store: raw OCR output, GPT responses, uploaded images. These are ephemeral.
- In production: migrate to Azure SQL with encryption at rest, implement data retention policies per federal records requirements.

## Error Responses

- Never expose stack traces, internal file paths, or Python exception details to the frontend.
- API errors return consistent JSON: `{"error": "message", "detail": "additional context"}`.
- If Azure Vision returns an error, return "Image processing failed — please try a clearer image" to the frontend. Log the Azure error details server-side.
- If GPT returns an error, return "Field extraction failed — please try again" to the frontend. Log the GPT error details server-side.
- Validation errors return 422 with Pydantic's field-level error details (this is safe — it describes the request shape, not internal state).

```python
# CORRECT: Generic user-facing error, detailed server-side log
@app.exception_handler(OCRExtractionError)
async def ocr_error_handler(request, exc):
    logger.error("OCR extraction failed", extra={"error": str(exc), "endpoint": request.url.path})
    return JSONResponse(
        status_code=502,
        content={"error": "Image processing failed", "detail": "Please try uploading a clearer image"},
    )
```

## CORS

- Default: allow `http://localhost:5173` (Vite dev server) and the production frontend origin.
- Do not use `*` in production — enumerate allowed origins explicitly.
- API keys are server-side only — never sent in browser requests.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
```

## Docker Security

- Don't run as root in the container. Use a non-root user.
- Use specific image tags (`python:3.11-slim`, `node:20-alpine`), not `latest`.
- Don't copy `.env` files into the Docker image.
- Multi-stage build: build stage installs deps and builds frontend, runtime stage copies only the app + static assets.
- Don't expose unnecessary ports. Only `8000` for the FastAPI server.
- Set `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` in the container.

```dockerfile
# Example multi-stage Dockerfile structure
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
RUN useradd --create-home appuser
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./static
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Dependencies

- Pin Python dependencies via `requirements.txt` with exact versions (committed to git).
- Pin Node dependencies via `package-lock.json` (committed to git).
- Key Python dependencies:
  - `fastapi` — Web framework
  - `uvicorn` — ASGI server
  - `httpx` — Async HTTP client for Azure and OpenAI
  - `python-multipart` — File upload handling
  - `pydantic` — Request/response validation
  - `sqlalchemy` — Database ORM
  - `fuzzywuzzy` + `python-Levenshtein` — Fuzzy string matching
  - `Pillow` — Image validation and preprocessing
  - `python-dotenv` — Environment variable loading
- Key Node dependencies:
  - `react`, `react-dom` — UI framework
  - `vite` — Build tool
  - `tailwindcss` — Styling
- Before adding a new dependency, check if the standard library covers the need. Keep the dependency tree minimal — this is a prototype that evaluators will inspect.

## Git Hygiene

- **Before committing, verify no secrets were accidentally added:**
  ```bash
  git diff --cached | grep -iE "(api_key|secret|password|token|sk-)" | grep -v "test\|mock\|example\|getenv\|env\.\|\.example"
  ```
  Review any matches.
- Never commit `.env` files, API keys, or database files.
- The `test_labels/` directory contains sample label images. These are synthetic/public-domain and safe to commit. Do not commit real TTB label submissions.
