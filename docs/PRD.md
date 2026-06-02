# Product Requirements Document
## TTB Label Verification Tool

**Version:** 1.0 (Prototype)
**Date:** June 2026
**Status:** In Development

---

## 1. Problem Statement

The Alcohol and Tobacco Tax and Trade Bureau (TTB) reviews approximately 150,000 Certificate of Label Approval (COLA) applications per year. A team of 47 compliance agents manually compares printed label artwork against submitted application data — verifying that the brand name, alcohol content, government warning statement, and other required fields on the physical label match what the applicant declared.

This process is almost entirely visual matching. Agents spend an estimated 50% of their review time on data-entry-level verification ("Is the number on the label the same as the number on the form?"), leaving less capacity for the nuanced compliance judgments that require human expertise.

A previous vendor pilot using automated label scanning failed due to unacceptable processing latency (30-40 seconds per label). Agents abandoned the tool and reverted to manual review within days.

### Core Opportunity

Automate the mechanical matching portion of label review so agents can focus on judgment-intensive compliance work. The tool must be fast enough that agents prefer it over manual eyeballing, and simple enough that the least tech-comfortable team members adopt it without training.

---

## 2. Users & Stakeholders

### Primary Users: Compliance Agents (47 total)

| Persona | Representative | Key Characteristics | Design Implications |
|---------|---------------|---------------------|---------------------|
| **Tech-cautious veteran** | Dave Morrison, 28 years | Prints emails, skeptical of automation, deep domain knowledge, has seen modernization projects fail | UI must be immediately obvious. No hunting for buttons. Tool must assist, never override. Dave will abandon anything that feels slower than his current process. |
| **Digital-native junior** | Jenny Park, 8 months | Uses a printed checklist, shocked by manual processes, understands the exact compliance rules | Tool should mirror her mental checklist. She'll be the first adopter and internal champion if the tool works. She'll catch edge cases others miss. |
| **Average agent** | Unnamed, 50+ | Half the team is over 50, varying comfort with technology | Font sizes, contrast, click targets, and cognitive load all matter. Sarah described the bar: "something my mother could figure out — she's 73." |

### Secondary Stakeholders

| Stakeholder | Role | Priorities |
|-------------|------|------------|
| **Sarah Chen** | Deputy Director, Label Compliance | Throughput improvement, staff satisfaction, batch processing for peak season |
| **Marcus Williams** | IT Systems Administrator | Azure alignment, security posture, no COLA integration scope creep, realistic about timeline |
| **Janet (Seattle)** | Office lead (mentioned) | Batch upload capability — has been requesting this for years |

### Non-Users (but relevant)

- **Label applicants** — Importers and producers who submit 200-300 labels at once during peak season. They don't use this tool, but their batch submission patterns create the batch processing requirement.
- **TTB leadership** — Evaluating whether AI can improve compliance operations. This prototype informs future procurement decisions.
- **COLA system maintainers** — The existing .NET system is out of scope for integration, but the prototype must not create dependencies that complicate future integration.

---

## 3. Requirements

### 3.1 Functional Requirements

#### FR-1: Single Label Verification (Must Have)

The system shall accept a single label image and application data, extract text from the image, and compare each field against the application data, returning a per-field verdict.

**Acceptance Criteria:**
- Agent uploads one image (JPEG, PNG, or single-page PDF)
- Agent enters application data via form fields (brand name, ABV, class/type, net contents, warning statement, producer, country of origin)
- System returns a verdict for each field: MATCH, MISMATCH, WARNING, or NOT_FOUND
- Results display the extracted value alongside the expected value for each field
- Each comparison includes a human-readable explanation (e.g., "Case difference only — exact match after normalization")
- Agent makes final determination — the tool recommends, the agent decides

#### FR-2: Government Warning Statement Verification (Must Have)

The system shall verify that the government health warning statement on the label matches the required text exactly, including the "GOVERNMENT WARNING:" header in all caps.

**Acceptance Criteria:**
- Warning statement comparison uses exact matching after whitespace normalization
- "Government Warning:" in title case is flagged as MISMATCH (not WARNING) — per TTB regulations, the header must be all caps
- Missing warning statement is flagged as NOT_FOUND
- Truncated or modified warning text is flagged as MISMATCH
- Extra whitespace between words does not cause a false mismatch

**Source:** Jenny Park — "The 'GOVERNMENT WARNING:' part has to be in all caps and bold. I caught one last month where they used 'Government Warning' in title case instead of all caps. Rejected."

#### FR-3: Fuzzy Matching for Text Fields (Must Have)

The system shall use fuzzy string matching for fields where minor variations are acceptable (brand name, producer), distinguishing between exact matches, near-matches requiring review, and clear mismatches.

**Acceptance Criteria:**
- Brand names differing only in case produce MATCH (e.g., "STONE'S THROW" vs "Stone's Throw")
- Minor OCR errors produce WARNING for human review (e.g., "DISTILLERV" vs "DISTILLERY")
- Genuinely different values produce MISMATCH (e.g., "MOUNTAIN CREEK" vs "OLD TOM DISTILLERY")
- Similarity scores are visible to the agent
- Thresholds are configurable (defaults: ≥0.95 = MATCH, 0.85–0.94 = WARNING, <0.85 = MISMATCH)

**Source:** Dave Morrison — "The brand name was 'STONE'S THROW' on the label but 'Stone's Throw' in the application. Technically a mismatch? Sure. But it's obviously the same thing."

#### FR-4: ABV Numeric Comparison (Must Have)

The system shall extract numeric alcohol content values from various label formats and compare them against the application data.

**Acceptance Criteria:**
- "45% Alc./Vol. (90 Proof)" matches application value "45"
- "90 Proof" matches application value "45" (proof ÷ 2 = ABV)
- "13.5%" matches "13.5"
- Numeric tolerance of ±0.5% produces WARNING, greater difference produces MISMATCH

#### FR-5: Batch Upload (Should Have)

The system shall support uploading multiple label images with corresponding application data for batch processing.

**Acceptance Criteria:**
- Agent uploads up to 50 label images simultaneously
- Agent provides application data for each label (via form or JSON upload)
- System processes labels and displays a summary table
- Summary shows overall pass/fail counts and allows drill-down to individual label results
- Agent can filter batch results by status (show mismatches only)
- Progress indicator shows how many labels have been processed

**Source:** Sarah Chen — "During peak season, we get these big importers who dump 200, 300 label applications on us at once. Right now we literally have to process them one at a time."

**Note:** The prototype caps batch size at 50. Production would use a job queue for the full 200-300 label batches Janet has been requesting.

#### FR-6: Verification History (Should Have)

The system shall persist verification results and allow agents to query past results.

**Acceptance Criteria:**
- Every verification result is stored with timestamp, field results, and overall status
- Agent can view recent verifications in reverse chronological order
- Agent can filter by status (PASS, REVIEW_NEEDED, FAIL)
- Results are paginated (default 20 per page)

#### FR-7: Image Quality Feedback (Nice to Have)

The system shall assess uploaded image quality and provide actionable feedback when images are suboptimal.

**Acceptance Criteria:**
- System attempts extraction on all readable images rather than rejecting imperfect ones
- When image quality issues are detected (glare, angle, blur, low resolution), they are noted in the result
- Low-confidence extractions are flagged with WARNING rather than presented as definitive
- If the image is completely unreadable, system returns a clear message suggesting the agent request a better image

**Source:** Jenny Park — "It would be amazing if the tool could handle images that aren't perfectly shot. I've seen labels that are photographed at weird angles, or the lighting is bad, or there's glare on the bottle."

### 3.2 Non-Functional Requirements

#### NFR-1: Processing Speed — Sub-5-Second Response

Single label verification must complete in under 5 seconds end-to-end (image upload to results display). This is the single hardest constraint and the reason the previous vendor pilot failed.

**Source:** Sarah Chen — "If we can't get results back in about 5 seconds, nobody's going to use it. We learned that the hard way."

**Budget Allocation:**
| Step | Target | Notes |
|------|--------|-------|
| Image upload | <500ms | Depends on file size and network |
| Azure AI Vision OCR | <2000ms | Typically 1-1.5s for label-sized images |
| GPT-4o field extraction | <2000ms | Text-only call, low token count |
| Comparison engine | <50ms | Pure Python, no I/O |
| Response serialization | <50ms | Pydantic model serialization |
| **Total** | **<5000ms** | |

#### NFR-2: Usability — Zero Training Required

The interface must be usable without training, documentation, or explanation. The benchmark is Sarah Chen's description: "something my mother could figure out — she's 73 and just learned to video call her grandkids last year."

**Measurable criteria:**
- No more than 3 steps to complete a single verification (upload → enter data → view results)
- All interactive elements are at least 44x44px (touch target minimum)
- Body text minimum 16px
- Status indicators use color AND text/icon (not color alone)
- No hamburger menus, no hidden panels, no tooltips required for core workflow
- Error messages are plain English, not technical jargon

#### NFR-3: Azure Infrastructure Alignment

Technology choices should align with Treasury's existing Azure environment to minimize the path from prototype to production.

**Source:** Marcus Williams — "We're on Azure now after the migration in 2019."

**Implications for prototype:**
- Use Azure AI Vision for OCR (Azure-native, FedRAMP-authorized)
- Document the path to Azure OpenAI Service for production GPT access
- Deploy on Azure App Service (or document how to)
- Mention Azure SQL, Azure Key Vault, Azure AD in production roadmap

#### NFR-4: Security Posture

The prototype does not handle sensitive data, but must demonstrate security awareness appropriate for a government environment.

**Source:** Marcus Williams — "Security-wise, we'd need to be careful with any production deployment — there's PII considerations, document retention policies, the usual federal compliance stuff. But for a prototype? Just don't do anything crazy."

**Prototype requirements:**
- API keys from environment variables only, never hardcoded
- No PII stored in the database (verification results only, no personal agent data)
- Input validation on all uploads (type, size, filename sanitization)
- Error responses do not expose internal state or stack traces
- Production roadmap addresses FedRAMP, Azure AD, encryption, data retention

#### NFR-5: Standalone Operation

The prototype must operate independently of the COLA system. No integration with existing TTB systems.

**Source:** Marcus Williams — "For this prototype, we're not looking to integrate with COLA directly — that's a whole different beast with its own authorization requirements."

---

## 4. Scope

### In Scope (Prototype)

- Single label image upload and verification
- Manual entry of application data via web form
- AI-powered text extraction from label images
- Per-field comparison with configurable matching strategies
- Three-level verdict system (MATCH / WARNING / MISMATCH)
- Batch upload (up to 50 labels)
- Verification history with filtering
- Deployed, accessible prototype URL
- Documentation of architecture, trade-offs, and production path

### Out of Scope (Prototype)

- COLA system integration (application data entry is manual)
- User authentication / role-based access control
- Multi-tenancy / multi-agent session management
- Bold/font-size verification of warning statement (text only, not typographic)
- Beverage-type-specific validation rules
- Multi-language label support
- Real-time label image capture (camera integration)
- Applicant-facing features
- Federal compliance certifications (FedRAMP, FISMA)

### Deferred to Production Roadmap

- Azure OpenAI Service migration (data stays within Azure tenant)
- Azure AD authentication
- COLA system read adapter
- Azure Functions for elastic batch scaling
- Beverage-type-specific rule engine
- Agent feedback loop for AI accuracy improvement
- Audit logging and data retention policies

---

## 5. Success Criteria

### Prototype Success (This Deliverable)

| Criterion | Measure | Target |
|-----------|---------|--------|
| **Core functionality works** | Single label verification returns correct per-field verdicts | All sample labels produce expected MATCH/MISMATCH verdicts |
| **Speed requirement met** | End-to-end processing time | < 5 seconds for single label |
| **Usability bar cleared** | A non-technical evaluator can complete a verification without instructions | Yes/No |
| **Batch upload functions** | Multiple labels processed with summary view | Process 10+ labels in one batch |
| **Code quality** | Clean structure, tests pass, no hardcoded secrets | All tests green, lint passes |
| **Architecture documented** | Trade-offs explained, production path outlined | README + architecture docs |

### Production Success (Future, Informational)

| Criterion | Measure | Target |
|-----------|---------|--------|
| Agent adoption | % of agents using tool daily after 30 days | > 70% |
| Time savings | Average review time per application | < 3 minutes (from 5-10) |
| Accuracy | False negative rate (tool says MATCH when there's a real mismatch) | < 1% |
| False alarm rate | False positive rate (tool says MISMATCH when it's fine) | < 10% |
| Batch throughput | Labels processed per hour during peak season | > 200 |

---

## 6. User Flows

### Flow 1: Single Label Verification (Primary)

```
Agent opens app
    │
    ▼
Sees upload zone (prominent, center of screen)
and application data form (alongside or below)
    │
    ├─► Drags label image onto upload zone
    │   (or clicks to browse files)
    │   Image preview appears
    │
    ├─► Enters application data in form fields:
    │   - Brand name
    │   - Class/type
    │   - ABV
    │   - Net contents
    │   - Warning statement
    │   - Producer (optional)
    │   - Country of origin (optional)
    │
    ▼
Clicks "Verify Label" button
    │
    ▼
Loading indicator (< 5 seconds)
    │
    ▼
Results panel appears:
    ┌─────────────────────────────────────┐
    │  Overall: REVIEW NEEDED  ⚠️         │
    │                                     │
    │  ✅ Brand Name      MATCH   (0.98)  │
    │     "OLD TOM DISTILLERY"            │
    │                                     │
    │  ✅ ABV              MATCH   (1.00)  │
    │     "45% Alc./Vol." = "45"          │
    │                                     │
    │  ❌ Warning Statement MISMATCH      │
    │     "Government Warning: ..."       │
    │     Expected: "GOVERNMENT WARNING:" │
    │     Note: Header not in all caps    │
    │                                     │
    │  ✅ Net Contents     MATCH   (1.00)  │
    │     "750 mL"                        │
    │                                     │
    │  ⚠️ Producer         WARNING (0.89)  │
    │     "Old Tom Dist., Louisville KY"  │
    │     Expected: "Old Tom Distillery,  │
    │     Louisville, KY"                 │
    └─────────────────────────────────────┘
    │
    ▼
Agent reviews results, makes determination
Agent can upload another label (form resets)
```

### Flow 2: Batch Verification

```
Agent clicks "Batch Upload" tab/mode
    │
    ▼
Sees multi-file upload zone
    │
    ├─► Drags multiple label images (up to 50)
    │   File count and names displayed
    │
    ├─► Uploads application data JSON
    │   (or enters data per label)
    │
    ▼
Clicks "Verify Batch"
    │
    ▼
Progress bar: "Processing 12 of 50 labels..."
    │
    ▼
Batch summary table appears:
    ┌──────────────────────────────────────────┐
    │  Batch Results: 50 labels                │
    │  ✅ 38 Pass  ⚠️ 8 Review  ❌ 4 Fail      │
    │                                          │
    │  [Show All] [Mismatches Only] [Warnings] │
    │                                          │
    │  Label          Status    Issues         │
    │  bourbon_01     ✅ PASS    —             │
    │  wine_02        ❌ FAIL    Warning text  │
    │  beer_03        ⚠️ REVIEW  Brand name    │
    │  ...                                     │
    └──────────────────────────────────────────┘
    │
    ▼
Agent clicks a row to see full field-by-field detail
(same view as single label results)
```

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| OCR accuracy too low on stylized fonts | Medium | High — agents lose trust | Flag low-confidence extractions as WARNING, never auto-approve. Show raw extracted text so agent can verify. |
| GPT extracts fields incorrectly (wrong field assignment) | Medium | High — silent errors | Comparison engine catches most misassignments as mismatches. Expose extracted values next to expected values so agent can spot errors visually. |
| Processing time exceeds 5 seconds | Low | Critical — tool will be abandoned (precedent exists) | Budget each pipeline step. Monitor timing. If GPT is slow, consider falling back to regex-based extraction for simple fields. |
| Agents don't trust the tool | Medium | High — zero adoption | Tool recommends, agent decides. Show the evidence (extracted text, similarity scores). Never hide the reasoning. Dave needs to see why before he trusts it. |
| Batch processing overwhelms API rate limits | Medium | Medium — batch fails partway | Implement concurrency limits (semaphore). Process sequentially if rate-limited. Show partial results as they complete. |
| Azure network blocks OpenAI API calls | Low (prototype) | High (production) | Prototype uses public OpenAI API. Production roadmap migrates to Azure OpenAI Service (on-network). Document this explicitly. |

---

## 8. Open Questions

| # | Question | Current Assumption | Impact if Wrong |
|---|----------|-------------------|-----------------|
| 1 | Should the tool auto-populate application data from a COLA export file? | Manual entry only (no COLA integration per Marcus) | Significant UX improvement if we support CSV/JSON import of application data |
| 2 | What is the acceptable false-positive rate? | <10% (tool flags a match as mismatch) | If too high, agents will ignore warnings. If too low, agents will over-trust. |
| 3 | Should the tool detect bold/font-size for the warning statement? | Text-only verification (prototype scope) | Jenny mentioned this matters. Would require image analysis beyond OCR. |
| 4 | Is there a standard format for application data export from COLA? | No — agents enter data manually | If COLA can export JSON/CSV, batch processing UX improves dramatically |
| 5 | How should the tool handle multi-panel labels (front + back)? | Single image per label | Some labels split required info across panels. Would need multi-image upload per label. |
