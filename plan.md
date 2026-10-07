# BhoomiLens — Mandatory Sarvam Document Extraction Fix

## Objective

Fix the document-analysis pipeline so that Sarvam Document AI is always attempted first for document extraction whenever a Sarvam API key is configured, regardless of the selected reasoning provider.

The selected reasoning provider (ollama, gemini, grok, sarvam, etc.) must NOT decide which provider performs document extraction.

Required behavior:

Uploaded PDF
 -> Native PDF text extraction
 -> Sarvam Document AI extraction FIRST
 -> SUCCESS: structured extraction
 -> FAIL: AI vision/OCR fallback (Ollama / Gemini / configured AI)

For this requirement:
1. Sarvam must be attempted first for extraction if SARVAM_API_KEY exists.
2. reasoning_provider=ollama must only select the reasoning/explanation model.
3. If Sarvam extraction fails, log the exact reason and then use AI vision/OCR.
4. If Sarvam succeeds, Ollama/Gemini must NOT redundantly re-extract the same document.
5. Test with the actual Udran_Khatoni.pdf scanned PDF.
6. Antigravity must run backend tests and an end-to-end document analysis before completion.

## 1. Root Cause Found in Current Repository

Repository: adityaksx/TeamVARS-Bhomi

Relevant files:
- backend/app/services/pipeline.py
- backend/app/services/fallback_extraction.py
- backend/app/core/config.py
- backend/tests/test_document_pipeline_failures.py
- backend/tests/test_digitise_and_reporting.py

### Root cause A — reasoning provider incorrectly controls extraction

Current pipeline logic effectively does:

    extraction_provider = reasoning_provider

    if sarvam_api_key and extraction_provider in {"auto", "fallback", "sarvam"}:
        # Sarvam extraction

When the frontend calls:

    POST /api/cases/{case_id}/analyze?reasoning_provider=ollama

extraction_provider becomes ollama, so the Sarvam condition is false.

The observed log proves this:

    stage=ocr_fallback
    Attempting Ollama vision extraction with model 'qwen3-vl:4b'

No Sarvam submission appears immediately before it.

### Required fix

Create two independent concepts:

    reasoning_provider
    extraction_provider

Example:

    reasoning_provider = "ollama"
    extraction_provider = "sarvam"

The UI may choose Ollama/Gemini/etc. for reasoning, while extraction follows the mandatory Sarvam-first policy.

## 2. Root Cause B — fallback_extraction.py bypasses Sarvam

backend/app/services/fallback_extraction.py currently handles scanned PDFs approximately as:

    no native text
     -> Gemini vision
     -> Ollama vision
     -> fail

There is no Sarvam Document AI call in this function.

Therefore any path entering extract_with_fallback() can bypass Sarvam.

### Required fix

Do not make fallback_extraction.py silently choose Sarvam independently if the main pipeline owns the Sarvam job lifecycle.

Centralize the extraction policy so there is exactly one authoritative extraction path.

Preferred design:

    pipeline.py
       |
       +--> native text detection
       |
       +--> mandatory Sarvam extraction
       |
       +--> AI vision fallback only after Sarvam failure

fallback_extraction.py should remain responsible for AI/OCR fallback providers, not silently override the mandatory Sarvam-first policy.

If reusable Sarvam code is needed, move _submit_sarvam, _poll_sarvam and result parsing into backend/app/services/sarvam_document_ai.py.

## 3. Required Provider Policy

### Sarvam API key exists

    SARVAM_API_KEY configured
          |
          v
    Sarvam Document AI MUST be attempted
          |
          +--> success -> use Sarvam result
          |
          +--> failure -> AI fallback

Selected reasoning provider must not change this.

| reasoning_provider | extraction order |
|---|---|
| ollama | Sarvam -> Ollama/Gemini fallback |
| gemini | Sarvam -> Gemini/Ollama fallback |
| grok | Sarvam -> Grok/other configured fallback |
| sarvam | Sarvam -> configured fallback |
| auto | Sarvam -> configured fallback |
| mock | preserve explicit mock/test behavior |

### No Sarvam API key

Use the existing AI/OCR fallback chain.

Do not claim Sarvam was attempted when no key exists.

## 4. Separate Extraction From Reasoning

Refactor analyze_case() so reasoning_provider is used only for downstream reasoning/explanation.

Add an extraction policy equivalent to:

    def resolve_extraction_provider(settings):
        if settings.sarvam_api_key:
            return "sarvam"
        return "fallback"

Do not derive extraction provider from reasoning_provider.

## 5. Preserve Existing Sarvam Document AI Implementation

The repository already has:
- _submit_sarvam()
- _poll_sarvam()
- _extract_result()
- Sarvam extraction schema
- chunked PDF handling
- optional Sarvam Digitise support
- source-page handling

Do not rewrite these blindly. First make them the mandatory first extraction path.

Existing flow:

    PDF
     -> split_pdf()
     -> /doc-ai/v1/job/extract
     -> job_id
     -> /status
     -> /results?format=json
     -> structured result

Keep this architecture unless current API behavior requires a targeted correction.

## 6. Important Sarvam API Error Handling

A previous BhoomiLens error was:

    CLASSIFICATION_NOT_SUPPORTED:
    classification is not supported on extract yet

Do NOT interpret this as an invalid API key.

It is a request/capability/API-contract problem.

The current extraction request includes:

    form = {
        "schema": EXTRACTION_SCHEMA,
        "language": settings.sarvam_document_language,
        "output_format": "json",
    }

Verify the current Sarvam Document AI Extract API contract before changing this.

If classification is being injected indirectly by the request/schema, remove only the unsupported classification behavior. Do not remove structured extraction itself.

## 7. Sarvam Extraction Must Work for Scanned PDFs

The test document is Udran_Khatoni.pdf, a 3-page scanned/image PDF.

Expected flow:

    Udran_Khatoni.pdf
        |
        v
    native PyMuPDF text extraction
        |
        v
    0 usable characters
        |
        v
    stage = sarvam_extraction
        |
        v
    Sarvam Document AI
        |
        v
    structured JSON
        |
        v
    normalization
        |
        v
    reconciliation

It must NOT immediately become:

    stage = ocr_fallback
        |
        v
    Ollama qwen3-vl:4b

unless Sarvam actually failed.

## 8. Required Logging

Add unambiguous logs.

Before Sarvam:
    stage=sarvam_extraction
    Starting mandatory Sarvam Document AI extraction for <filename>

Job creation:
    Sarvam Document AI job submitted: document=<id> job_id=<id>

Polling:
    Sarvam Document AI job status: job_id=<id> status=<status>

Success:
    Sarvam Document AI extraction succeeded: document=<id> job_id=<id> pages=<count>

Failure:
    Sarvam Document AI extraction failed: document=<id> status=<http status> error_code=<normalized code> message=<sanitized message>

Fallback:
    Sarvam extraction failed; entering AI vision/OCR fallback provider=<provider>

Never log API keys, Authorization headers, base64 images, or full private OCR output.

## 9. Add Explicit Extraction Metadata

Each processed document should retain enough metadata to diagnose what happened.

Recommended fields:

    extraction_provider
    extraction_attempted_providers
    extraction_fallback_used
    extraction_error
    extraction_job_id

Successful Sarvam example:

    {
      "extraction_provider": "sarvam",
      "extraction_attempted_providers": ["sarvam"],
      "extraction_fallback_used": false,
      "extraction_job_id": "..."
    }

Sarvam failure followed by Ollama:

    {
      "extraction_provider": "ollama",
      "extraction_attempted_providers": ["sarvam", "ollama"],
      "extraction_fallback_used": true,
      "extraction_error": "..."
    }

Do not replace reasoning_provider with these fields.

## 10. AI Vision Fallback Rules

After Sarvam fails:

For scanned/image-only PDFs, use qwen3-vl:4b when Ollama is configured and selected as the fallback.

Gemini can be used if configured.

Critical rule:

AI vision fallback must never run before the Sarvam attempt when a Sarvam key is configured.

## 11. JSON Robustness

The current Ollama failure was:

    INVALID_JSON_RESPONSE
    AI extraction did not return JSON:
    <think>...

This is a second independent issue.

Improve fallback parsing/prompt handling so that:
1. structured output is requested where supported;
2. <think>...</think> blocks are removed before JSON parsing;
3. fenced JSON is handled;
4. the first valid JSON object is extracted safely;
5. malformed JSON still produces INVALID_JSON_RESPONSE.

Do not weaken validation so much that arbitrary model prose is accepted as extracted data.

Add unit tests for:
- <think>...</think>{"document_type":"Khatauni"}
- fenced JSON
- plain JSON
- invalid prose

## 12. Do Not Use Sarvam Digitise as a Substitute for Extract

SARVAM_DIGITISE_ENABLED is optional and currently defaults to false.

Digitise is used for source anchors/visual evidence.

Do not confuse:
- /doc-ai/v1/job/extract
- /doc-ai/v1/job/digitise

Primary extraction must use Sarvam Document AI Extract.

Optional evidence/anchor enrichment may use Sarvam Digitise.

## 13. Tests To Add

### Test 1 — reasoning provider must not bypass Sarvam

Mock:
    sarvam_api_key = "test-key"
    reasoning_provider = "ollama"

Assert _submit_sarvam() is called before Ollama vision extraction.

Assert Ollama is not called if Sarvam succeeds.

### Test 2 — Sarvam failure triggers vision fallback

Mock:
    Sarvam -> raises RuntimeError
    Ollama vision -> valid JSON

Expected:
    provider = "ollama"
    fallback_used = True
    attempts = ["sarvam", "ollama"]

### Test 3 — Sarvam success prevents duplicate AI extraction

Mock Sarvam to return valid structured data and make Ollama fail if called.

Expected successful analysis without Ollama.

### Test 4 — no Sarvam key

Mock:
    sarvam_api_key = None

Expected existing AI/OCR fallback behavior.

### Test 5 — scanned PDF

Mock:
    extract_text() -> ""

Assert sarvam_extraction occurs before ocr_fallback.

### Test 6 — reasoning provider remains independent

Run analysis with reasoning_provider=ollama and reasoning_provider=gemini.

With a Sarvam key, both must attempt Sarvam first.

### Test 7 — Ollama <think> response

Input:
    <think>
    reasoning
    </think>
    {"document_type":"Khatauni"}

Expected parsed object:
    {"document_type":"Khatauni"}

## 14. End-to-End Test With Real PDF

Antigravity must use the actual project test document:

    Udran_Khatoni.pdf

Run:
1. Start Ollama.
2. Start FastAPI.
3. Ensure Sarvam API key is configured.
4. Upload Udran_Khatoni.pdf.
5. Create a case.
6. Run analysis with reasoning_provider=ollama.
7. Watch backend logs.

### Required log order for successful Sarvam

    detecting_document
    -> sarvam_extraction
    -> Sarvam job submitted
    -> polling
    -> Sarvam completed
    -> normalizing
    -> completed

This must NOT occur:

    sarvam_extraction skipped
    -> ocr_fallback
    -> Ollama vision

If Sarvam genuinely fails, expected order is:

    detecting_document
    -> sarvam_extraction
    -> Sarvam failed
    -> ocr_fallback / ai_extraction
    -> Ollama vision
    -> normalizing
    -> completed

## 15. Test the Actual Sarvam Failure Scenario

Antigravity must intentionally reproduce the previous CLASSIFICATION_NOT_SUPPORTED error if possible.

Record:
- HTTP status
- response JSON
- request parameters except secrets
- whether schema caused the issue
- whether language caused the issue
- whether output_format caused the issue
- exact current API endpoint
- whether the endpoint is still supported

Then implement the smallest compatible fix.

Do not silently swallow the error and route to Ollama.

The log must explicitly state:

    Sarvam attempted: YES
    Sarvam failed: YES
    Reason: <exact reason>
    Fallback started: YES

## 16. Do Not Couple Provider Settings

The frontend currently sends:

    /cases/{case_id}/analyze?reasoning_provider=ollama

Keep this API contract if possible.

Do NOT reinterpret this query parameter as extraction_provider.

Correct separation:

    reasoning_provider -> reasoning
    extraction_provider -> automatic policy

If an explicit extraction override is useful, make it a separate parameter. The default must remain:

    if Sarvam key exists -> Sarvam first

## 17. Preserve Mock Mode

Existing mock behavior is used for deterministic testing.

Do not break reasoning_provider=mock.

Mock tests may intentionally bypass external providers. Document this exception.

## 18. Required Files To Inspect/Modify

Inspect before editing:
- backend/app/services/pipeline.py
- backend/app/services/fallback_extraction.py
- backend/app/core/config.py
- backend/app/api/routes.py
- backend/app/providers/
- backend/tests/test_document_pipeline_failures.py
- backend/tests/test_digitise_and_reporting.py
- frontend/components/BhoomiConsole.tsx

Likely modified:
- backend/app/services/pipeline.py
- backend/app/services/fallback_extraction.py
- backend/app/services/sarvam_document_ai.py if useful
- backend/tests/test_document_pipeline_failures.py
- backend/tests/test_sarvam_extraction.py

Do not make unrelated frontend or reconciliation changes.

## 19. Implementation Sequence

1. Audit current provider routing.
2. Separate reasoning_provider from extraction_provider.
3. Force Sarvam first whenever SARVAM_API_KEY exists.
4. Preserve AI vision fallback after Sarvam failure.
5. Fix Ollama <think>/JSON parsing.
6. Add extraction metadata and logging.
7. Add unit tests.
8. Run the full backend test suite.
9. Run the real Udran_Khatoni.pdf E2E test.
10. Verify logs prove actual provider order.
11. Verify structured extraction reaches normalization/reconciliation.

## 20. Verification Commands

Use the project's actual virtual environment.

Typical:

    cd /mnt/data/Code/TeamVARS-Bhomi
    cd backend
    pytest -q
    pytest -q tests/test_document_pipeline_failures.py
    pytest -q tests/test_digitise_and_reporting.py

Ollama:

    curl http://127.0.0.1:11434/api/tags
    ollama list
    ollama ps

GPU:

    nvidia-smi

Then run FastAPI and perform the real upload/analyze flow.

Do not declare success from unit tests alone.

## 21. Acceptance Criteria

- [ ] Sarvam is attempted whenever a Sarvam API key is configured.
- [ ] reasoning_provider=ollama no longer bypasses Sarvam.
- [ ] Scanned PDFs enter sarvam_extraction before any AI vision fallback.
- [ ] Successful Sarvam extraction prevents duplicate Ollama/Gemini extraction.
- [ ] Failed Sarvam extraction triggers AI vision/OCR fallback.
- [ ] Exact Sarvam failure is logged.
- [ ] reasoning_provider remains independent from extraction routing.
- [ ] Ollama <think> responses no longer cause avoidable JSON failures.
- [ ] Existing mock tests still work.
- [ ] Unit tests cover Sarvam success and failure.
- [ ] Udran_Khatoni.pdf is tested end-to-end.
- [ ] Backend test suite passes.
- [ ] Final terminal logs prove actual provider order.
- [ ] No API keys or document contents are leaked in logs.

## 22. Mandatory Final Report From Antigravity

Print:

    BHOOMILENS SARVAM EXTRACTION VERIFICATION
    ==========================================

    Document:
    Udran_Khatoni.pdf

    Native text:
    <CHAR_COUNT>

    Sarvam key configured:
    YES / NO

    Sarvam extraction attempted:
    YES / NO

    Sarvam job ID:
    <job_id or N/A>

    Sarvam result:
    SUCCESS / FAILED

    Sarvam failure:
    <exact sanitized error or NONE>

    Fallback provider:
    <NONE / Ollama / Gemini / other>

    Fallback required:
    YES / NO

    Final extraction provider:
    <Sarvam / Ollama / Gemini / ...>

    Reasoning provider:
    <ollama / gemini / ...>

    Sarvam before fallback:
    PASS / FAIL

    Duplicate extraction avoided:
    PASS / FAIL

    Structured extraction:
    PASS / FAIL

    Normalization:
    PASS / FAIL

    Reconciliation:
    PASS / FAIL

    Backend tests:
    PASS / FAIL

    End-to-end test:
    PASS / FAIL

    ROOT CAUSE:
    <one concise paragraph>

    FILES CHANGED:
    <list>

    FINAL STATUS:
    PASS / FAIL

Do not report PASS unless the real document flow was executed.

## 23. Non-Negotiable Architectural Constraint

Do not solve this by changing the frontend dropdown to Sarvam.

The backend must enforce Sarvam-first extraction.

Even if the frontend sends:

    reasoning_provider=ollama

the correct architecture is:

    Sarvam Document AI extraction
            |
            v
    structured document
            |
            v
    Ollama reasoning

That separation is the actual fix.
