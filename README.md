# TTB Label Verification Tool

An AI-powered prototype for automating alcohol beverage label compliance checks. Built for the Treasury Department's Alcohol and Tobacco Tax and Trade Bureau (TTB), where 47 agents manually review ~150,000 label applications per year by visually comparing printed labels against submitted application data.

This tool extracts text from label images using Azure AI Vision, structures the extracted data with GPT-4o, and programmatically verifies each field against the application — reducing a 5–10 minute manual review to under 5 seconds.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Tech Stack & Rationale](#tech-stack--rationale)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Design Decisions & Trade-offs](#design-decisions--trade-offs)
- [Production Roadmap](#production-roadmap)
- [Known Limitations](#known-limitations)

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Azure AI Vision API key ([Azure Portal](https://portal.azure.com))
- OpenAI API key ([platform.openai.com](https://platform.openai.com))

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # Add your API keys
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env            # Set API URL
npm run dev
```

The UI runs at `http://localhost:5173`.

### Environment Variables

```
# backend/.env
AZURE_VISION_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com
AZURE_VISION_KEY=<your-key>
OPENAI_API_KEY=<your-key>
DATABASE_URL=sqlite:///./verification.db
```

```
# frontend/.env
VITE_API_URL=http://localhost:8000
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│                   React + Vite + Tailwind                   │
│                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │  Upload   │  │  Application │  │  Results Dashboard    │ │
│  │  Zone     │  │  Data Form   │  │  (per-field verdicts) │ │
│  └──────────┘  └──────────────┘  └───────────────────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────────┐
│                     Backend (FastAPI)                        │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  /verify     │  │  /batch      │  │  /history          │ │
│  │  single      │  │  multi-file  │  │  past results      │ │
│  └──────┬──────┘  └──────┬───────┘  └────────┬───────────┘ │
│         │                │                    │             │
│  ┌──────▼────────────────▼──────────┐  ┌─────▼──────────┐  │
│  │      Verification Pipeline       │  │    SQLite DB    │  │
│  │                                  │  │  (audit trail)  │  │
│  │  1. Azure AI Vision (OCR)        │  └────────────────┘  │
│  │  2. GPT-4o (field structuring)   │                      │
│  │  3. Comparison engine (Python)   │                      │
│  └──────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline Detail

```
Label Image
    │
    ▼
Azure AI Vision (OCR)
    │  Raw text extraction with bounding boxes
    ▼
GPT-4o (Structuring)
    │  "Given this raw OCR text from an alcohol label,
    │   extract: brand_name, class_type, abv, net_contents,
    │   warning_statement, producer, origin"
    ▼
Structured JSON
    │  { "brand_name": "OLD TOM DISTILLERY", "abv": "45%", ... }
    ▼
Comparison Engine (Python)
    │  Field-by-field verification against application data
    │  - Warning statement: exact match (after normalization)
    │  - ABV: numeric extraction + tolerance check
    │  - Brand name: fuzzy match (Levenshtein ratio ≥ 0.85)
    │  - Other fields: normalized string comparison
    ▼
Verification Result
    { field: "brand_name", status: "MATCH", confidence: 0.97,
      extracted: "OLD TOM DISTILLERY", expected: "Old Tom Distillery",
      note: "Case difference only — exact match after normalization" }
```

---

## How It Works

### Single Label Verification

1. Agent uploads a label image (JPEG, PNG, or PDF)
2. Agent enters the application data (brand name, ABV, class/type, etc.) or loads it from a previous submission
3. System extracts text from the image via Azure AI Vision
4. GPT-4o parses the raw OCR text into structured label fields
5. Comparison engine checks each field and returns MATCH / MISMATCH / WARNING
6. Agent reviews results and makes final determination

### Batch Verification

1. Agent uploads multiple label images (up to 50 per batch)
2. Agent enters or uploads corresponding application data
3. System processes each label asynchronously
4. Results display as a summary table with drill-down per label
5. Agent can filter by status (mismatches only, warnings, etc.)

### Verification Statuses

| Status | Meaning |
|--------|---------|
| ✅ MATCH | Extracted value matches application data |
| ❌ MISMATCH | Clear discrepancy — agent should review |
| ⚠️ WARNING | Possible match requiring human judgment (e.g., minor formatting differences) |
| ➖ NOT FOUND | Field could not be extracted from label image |

---

## Tech Stack & Rationale

Every technology choice maps to a project constraint or stakeholder requirement.

| Layer | Technology | Why This Choice |
|-------|-----------|-----------------|
| **OCR** | Azure AI Vision | Azure-native, aligns with Treasury's existing Azure infrastructure (FedRAMP-authorized). High accuracy on printed text. Sub-2-second extraction. |
| **Field Parsing** | OpenAI GPT-4o | Handles the unstructured-to-structured parsing that rule-based approaches can't — label layouts vary wildly across brands. Text-only call (not vision), so fast and cheap. |
| **Backend** | Python + FastAPI | Python is standard for AI/ML work. FastAPI provides async support for batch processing, auto-generated API docs, and Pydantic validation. Aligns with government data science teams. |
| **Frontend** | React + Vite + Tailwind | Component model fits the results display (each field as a reusable component). Tailwind enables rapid, consistent styling. Vite for fast dev iteration. |
| **Database** | SQLite | Zero-infrastructure persistence for verification audit trails. Appropriate for a prototype; production would migrate to Azure SQL or PostgreSQL. |
| **Deployment** | Azure App Service | Runs within Treasury's existing infrastructure. No additional FedRAMP authorization needed. Demonstrates the prototype could operate within their network constraints. |
| **Comparison** | Python (fuzzywuzzy + custom) | Deterministic, testable, transparent. Warning statement gets exact matching; brand names get fuzzy matching. Agents can see *why* something matched or didn't. |

### Why Two AI Services (Azure Vision + GPT)?

This was a deliberate architectural separation:

- **Azure AI Vision** handles what it's best at: extracting raw text from images with high accuracy, including on imperfect photos (glare, angles, poor lighting). It returns text with spatial/bounding box data.
- **GPT-4o** handles what it's best at: understanding context and structure. It takes the raw OCR dump and figures out which text is the brand name vs. the ABV vs. the warning statement, despite wildly varying label layouts.

An alternative would be sending images directly to a multimodal LLM (GPT-4o Vision). This is faster to implement but loses the Azure-native OCR story and makes the entire pipeline dependent on a single external API. The two-service approach is more resilient and more aligned with production federal architecture.

---

## Project Structure

```
ttb-label-verification/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan
│   │   ├── routers/
│   │   │   ├── verify.py        # Single label verification endpoint
│   │   │   ├── batch.py         # Batch upload and processing
│   │   │   └── history.py       # Verification history queries
│   │   ├── services/
│   │   │   ├── ocr.py           # Azure AI Vision integration
│   │   │   ├── parser.py        # GPT-4o field extraction
│   │   │   └── comparator.py    # Field comparison engine
│   │   ├── models/
│   │   │   ├── schemas.py       # Pydantic request/response models
│   │   │   └── database.py      # SQLite models and connection
│   │   └── utils/
│   │       ├── normalization.py # Text normalization helpers
│   │       └── constants.py     # Government warning text, field configs
│   ├── tests/
│   │   ├── test_comparator.py   # Comparison logic unit tests
│   │   ├── test_normalization.py
│   │   └── test_api.py          # Endpoint integration tests
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.jsx   # Drag-and-drop image upload
│   │   │   ├── ApplicationForm.jsx  # Application data entry
│   │   │   ├── ResultsPanel.jsx     # Verification results display
│   │   │   ├── FieldResult.jsx      # Individual field verdict
│   │   │   ├── BatchUpload.jsx      # Multi-file upload and progress
│   │   │   └── BatchResults.jsx     # Batch summary table
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── .env.example
├── test_labels/                 # Sample label images for testing
│   ├── bourbon_clean.png
│   ├── wine_angled.jpg
│   └── beer_glare.jpg
├── docs/
│   └── architecture-decisions.md
└── README.md
```

---

## API Reference

Full interactive documentation available at `/docs` when the backend is running.

### POST `/api/verify`

Verify a single label image against application data.

**Request** (multipart/form-data):
```
file: <image file>
application_data: {
  "brand_name": "OLD TOM DISTILLERY",
  "class_type": "Kentucky Straight Bourbon Whiskey",
  "abv": "45",
  "net_contents": "750 mL",
  "warning_statement": "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.",
  "producer": "Old Tom Distillery, Louisville, KY",
  "origin": "United States"
}
```

**Response**:
```json
{
  "id": "ver_abc123",
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
      "similarity": 1.0
    },
    {
      "field": "warning_statement",
      "status": "MISMATCH",
      "extracted": "Government Warning: ...",
      "expected": "GOVERNMENT WARNING: ...",
      "confidence": 0.95,
      "method": "exact_match",
      "note": "Header not in required ALL CAPS format"
    }
  ],
  "image_quality": {
    "readable": true,
    "issues": []
  }
}
```

### POST `/api/batch`

Submit multiple labels for batch processing.

### GET `/api/batch/{batch_id}`

Poll batch processing status and results.

### GET `/api/history`

Query past verification results (paginated).

---

## Design Decisions & Trade-offs

### 1. Two-Step AI Pipeline vs. Single Multimodal Call

**Decision:** Azure AI Vision for OCR → GPT-4o for structuring, rather than sending images directly to a multimodal LLM.

**Why:** Azure AI Vision is FedRAMP-authorized and runs within Azure's network boundary. In production, OCR processing stays on-network with no data leaving Treasury's Azure tenant. GPT-4o receives only extracted text, not the original label images, reducing the data exposure surface.

**Trade-off:** Two API calls add ~1-2 seconds of latency vs. a single multimodal call. Acceptable given the 5-second budget, and the security posture improvement justifies it for production.

### 2. Deterministic Comparison Engine vs. LLM-Based Matching

**Decision:** Python code handles all field comparisons, not the LLM.

**Why:** The government warning statement requires *exact* matching (per Jenny Park's feedback — "GOVERNMENT WARNING:" must be all caps). Deterministic code guarantees the same input always produces the same result. It's also unit-testable, auditable, and explainable — critical properties for a government compliance tool where decisions may be challenged.

**Trade-off:** Less flexible on edge cases. A brand name like "STONE'S THROW" vs. "Stone's Throw" is handled by fuzzy matching, but more exotic variations might need human review. The WARNING status exists for this purpose — flag it, don't auto-decide.

### 3. SQLite vs. No Database

**Decision:** Include SQLite for basic persistence.

**Why:** An audit trail is foundational for government compliance work. Even in a prototype, demonstrating that verification results are logged (with timestamps, agent context, and the full extraction/comparison record) shows production awareness. SQLite requires zero infrastructure.

**Trade-off:** Development time spent on schema and queries. Kept minimal — single table, simple queries, no complex relationships.

### 4. Separate Frontend and Backend vs. Monolith

**Decision:** React frontend communicating with a FastAPI backend via REST, rather than a full-stack framework like Next.js or a server-rendered approach.

**Why:** Separation reflects how this would be built in a government environment where frontend and backend teams often operate independently, and where the API might serve multiple clients (web UI, potential COLA integration, reporting tools). FastAPI's auto-generated OpenAPI docs make the API self-documenting for other teams.

**Trade-off:** More deployment complexity (two services). Additional CORS configuration. Justified by the architectural clarity and extensibility.

### 5. Fuzzy Match Threshold (0.85 Levenshtein Ratio)

**Decision:** Brand names and other text fields use a similarity threshold of 0.85 to determine MATCH vs. WARNING vs. MISMATCH.

**Why:** Accounts for minor OCR errors, case differences, and punctuation variations without auto-approving genuinely different text. Derived from testing against sample labels — "Stone's Throw" vs "STONE'S THROW" scores ~0.90 after normalization, while genuinely different names score below 0.70.

| Score | Verdict |
|-------|---------|
| ≥ 0.95 | MATCH |
| 0.85 – 0.94 | WARNING (human review) |
| < 0.85 | MISMATCH |

**Trade-off:** Any threshold is somewhat arbitrary. In production, this should be tunable per field and calibrated against historical agent decisions.

---

## Production Roadmap

This prototype demonstrates the core verification workflow. Moving to production within Treasury's environment would involve:

### Phase 1: Security & Compliance
- Migrate GPT-4o calls to Azure OpenAI Service (data stays within Azure tenant, FedRAMP-authorized)
- Replace SQLite with Azure SQL Database
- Implement Azure AD authentication (integrate with Treasury's identity provider)
- Add role-based access control (agent, supervisor, admin)
- Enable Azure Key Vault for secrets management
- Implement data retention and purging policies per federal records requirements

### Phase 2: COLA Integration
- Build read adapter for COLA system to pull application data automatically (eliminate manual data entry)
- Map COLA application IDs to verification results
- Develop webhook or polling mechanism for new application notifications

### Phase 3: Scale & Optimization
- Move batch processing to Azure Functions for elastic scaling
- Add Azure Blob Storage for label image archival
- Implement Azure Application Insights for monitoring and performance tracking
- Build agent performance dashboard (verification throughput, override rates)
- A/B test AI accuracy against agent decisions to calibrate thresholds

### Phase 4: Advanced Features
- Beverage-type-specific validation rules (beer, wine, spirits have different TTB requirements)
- Multi-language label support (import labels)
- Historical trend analysis (common rejection reasons, repeat offender tracking)
- Agent feedback loop to improve AI extraction accuracy over time

---

## Known Limitations

- **OCR accuracy on heavily stylized fonts:** Decorative or script-style brand names may extract poorly. The system flags low-confidence extractions for human review rather than guessing.
- **Warning statement formatting detection:** The prototype verifies the *text* of the warning statement but does not confirm typographic requirements (bold, minimum font size) from the image. This would require additional image analysis.
- **Batch size cap:** Limited to 50 labels per batch in the prototype to keep processing times reasonable. Production would use a job queue (Celery + Redis, or Azure Functions) for larger batches.
- **No offline mode:** Requires network access to Azure AI Vision and OpenAI APIs. A production deployment using Azure OpenAI Service within the Treasury Azure tenant would resolve the external dependency.
- **Single-user:** No authentication or multi-tenancy. The prototype assumes a single agent session. Production deployment requires Azure AD integration.
- **Image format support:** Accepts JPEG, PNG, and single-page PDF. Multi-page PDFs and TIFF files are not yet supported.

---

## Testing

```bash
cd backend
pytest tests/ -v
```

Test coverage focuses on the comparison engine, which contains the core business logic:
- Exact match verification for warning statements
- Fuzzy match scoring for brand names
- ABV numeric extraction and comparison
- Edge cases (empty fields, OCR artifacts, special characters)

---

## License

This project was built as a prototype for evaluation purposes.