# BhoomiLens AI Provider Connection — Antigravity Debug & Fix Plan

## Mission

Fix the AI-provider connection layer of TeamVARS-Bhomi / BhoomiLens for three providers:

1. Sarvam AI — user-supplied free API key
2. Google Gemini API — user-supplied free API key
3. Local Ollama — RTX 3050 6 GB

Current symptom: Sarvam does not connect, Gemini does not connect, and Ollama works but is too slow.

The first goal is **diagnostic certainty**. Do not debug the full document pipeline until each provider has passed a minimal standalone request.

---

## 1. Current environment

Installed Ollama models:

| Model | Size | Quantization | Role |
|---|---:|---|---|
| qwen3:8b | ~5.2 GB | Q4_K_M | Primary text/reasoning |
| deepseek-r1:8b | ~5.2 GB | Q4_K_M | Deep reasoning; slower |
| qwen3-vl:4b | ~3.3 GB | Q4_K_M | Vision/scanned documents/OCR |
| gemma3:4b | ~3.3 GB | Q4_K_M | Lightweight fallback |

Hardware: NVIDIA RTX 3050 Laptop GPU, 6 GB VRAM, Fedora Linux, Ollama installed.

Do not assume that an installed model is actually using the GPU efficiently.

---

## 2. Free-key requirement

The user has **free API keys, not paid accounts**.

Every diagnostic must distinguish:

- missing key
- malformed key
- invalid key
- valid key but model unavailable
- free-tier quota exhausted
- rate limited
- billing/account restriction
- endpoint/model mismatch
- malformed request
- timeout/network error
- provider 5xx
- application-side parsing/integration bug

Do not label every 401/403/429 as an invalid key.

Google's current documentation states that the free tier has limited model access, so the implementation must verify that the selected model is actually available to the supplied key/project.

Sarvam requires an API subscription key and currently documents both the api-subscription-key header and Bearer authentication.

---

## 3. Official references

Sarvam:
- Authentication: https://docs.sarvam.ai/api-reference/authentication
- Chat V1: https://docs.sarvam.ai/api-reference/chat/chat-completions-v1
- Chat V2: https://docs.sarvam.ai/api-reference/chat/chat-completions-v2
- Quickstart: https://docs.sarvam.ai/api/getting-started/quickstart
- Chat overview: https://docs.sarvam.ai/api/api-guides-tutorials/chat-completion/overview

Gemini:
- API docs: https://ai.google.dev/gemini-api/docs
- API keys: https://ai.google.dev/gemini-api/docs/api-key
- Gemini 3: https://ai.google.dev/gemini-api/docs/gemini-3
- Pricing/free tier: https://ai.google.dev/gemini-api/docs/pricing

Ollama:
- API: https://docs.ollama.com/api
- OpenAI compatibility: https://docs.ollama.com/openai

Do not copy old provider code from random repositories when the official API has changed.

---

## 4. Repository audit

Before editing, inspect:

~~~
backend/app/providers/
backend/app/api/routes.py
frontend/components/BhoomiConsole.tsx
frontend/
backend/
requirements.txt
pyproject.toml
package.json
.env*
~~~

Search for:

~~~
Sarvam
sarvam
Gemini
gemini
Ollama
ollama
X-Sarvam-Api-Key
X-Gemini-Api-Key
X-Ollama-Base-Url
X-Ollama-Model
/provider/test
/ollama/models
google-genai
sarvamai
~~~

Inspect the current implementation rather than assuming it matches this plan.

Do not rewrite unrelated application code.

---

## 5. Debug architecture

Use this flow:

~~~
Frontend Settings
      |
      v
POST /provider/test
      |
      v
Standalone provider adapter
      |
      +--> Sarvam
      +--> Gemini
      +--> Ollama
      |
      v
Normalized ProviderTestResult
      |
      v
Frontend diagnostic status
~~~

Production calls should eventually reuse the same provider adapters.

The testing path must not execute the complete PDF/OCR/reasoning pipeline.

---

## 6. Create isolated provider connection modules

If an equivalent abstraction already exists, extend it.

Recommended structure:

~~~
backend/
  app/
    providers/
      connections/
        __init__.py
        base.py
        models.py
        errors.py
        sarvam.py
        gemini.py
        ollama.py
        runner.py
  scripts/
    test_ai_connections.py
  tests/
    provider_connections/
      test_models.py
      test_sarvam.py
      test_gemini.py
      test_ollama.py
      test_runner.py
~~~

---

## 7. Normalized result contract

All providers should return the same structure.

Example fields:

~~~
provider
configured
connected
usable
model
http_status
latency_ms
attempts
retryable
error_code
error_message
raw_provider_status
~~~

Recommended error codes:

~~~
CONFIGURATION_ERROR
AUTHENTICATION_ERROR
AUTHORIZATION_ERROR
MODEL_NOT_AVAILABLE
INVALID_REQUEST
QUOTA_EXCEEDED
RATE_LIMITED
TIMEOUT
NETWORK_ERROR
PROVIDER_SERVER_ERROR
RESPONSE_PARSE_ERROR
OLLAMA_UNAVAILABLE
OLLAMA_MODEL_NOT_FOUND
UNKNOWN_PROVIDER_ERROR
~~~

Never return or log API keys.

---

## 8. Credential handling

Support environment variables for CLI diagnostics:

~~~
SARVAM_API_KEY=
GEMINI_API_KEY=
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=
~~~

The web UI must accept runtime keys.

Rules:

1. Do not persist raw API keys.
2. Do not put keys in database records.
3. Do not return keys to the frontend.
4. Do not print keys in logs.
5. Redact Authorization and API-key headers.
6. Do not commit .env secrets.
7. Prefer an interactive getpass prompt for local CLI tests.
8. Runtime browser keys may be forwarded only for the requested provider call.

---

# 9. Sarvam standalone connection test

First prove Sarvam chat connectivity. Do **not** start with Document AI.

Sarvam's current V1 chat endpoint documents sarvam-105b and sarvam-105b-conversations. Verify the exact model and endpoint from the current official documentation before making the request.

Minimal request:

~~~
user: Reply exactly: OK
~~~

No PDF, OCR, tools, huge context, or document text.

### Test matrix

S1. Missing key -> CONFIGURATION_ERROR

S2. Deliberately fake key -> AUTHENTICATION_ERROR

S3. Real free key -> minimal chat response

S4. Verify model is accessible to this account

S5. 429 -> RATE_LIMITED / QUOTA_EXCEEDED as appropriate

S6. Timeout -> TIMEOUT

S7. 5xx -> PROVIDER_SERVER_ERROR and bounded retry

S8. Successful response -> verify response parser extracts assistant text

Do not infer authentication failure from a generic exception.

---

## 10. Sarvam REST vs official SDK

Sarvam's official Python SDK is sarvamai.

If practical, test both:

1. direct documented REST call
2. official SDK call

Interpretation:

| REST | SDK | Diagnosis |
|---|---|---|
| pass | pass | provider/key works |
| fail | fail | provider/account/model/request issue |
| pass | fail | SDK integration issue |
| fail | pass | custom REST adapter issue |

Use the official docs as the primary contract.

---

## 11. Sarvam Document AI is separate

A previous BhoomiLens error was:

~~~
CLASSIFICATION_NOT_SUPPORTED:
classification is not supported on extract yet
~~~

Treat this as a possible **Document AI request/capability issue**, not proof that the API key is bad.

Test in this order:

~~~
Sarvam key
  -> minimal chat
  -> success
  -> Document AI test
~~~

For Document AI, verify current endpoint, supported parameters, job creation, polling/status flow, document type, and current capabilities from the official docs.

---

# 12. Gemini standalone connection test

Use Google's current official Gemini API/SDK.

The official Python package is google-genai.

Do not hardcode a model from an old tutorial.

First determine which current models are actually available to the supplied API key/project and free tier. Then run the smallest generation request.

Prompt:

~~~
Reply exactly: OK
~~~

Do not initially use:
- PDFs
- image input
- web search
- tools
- large system prompts
- structured output
- long context

This isolates authentication and basic generation.

---

## 13. Gemini test matrix

G1. Missing key -> CONFIGURATION_ERROR

G2. Fake key -> AUTHENTICATION_ERROR

G3. Real free key + verified free-tier model -> success

G4. Model unavailable -> MODEL_NOT_AVAILABLE

G5. Free quota exhausted -> QUOTA_EXCEEDED

G6. 429 -> RATE_LIMITED

G7. 5xx -> bounded retry

G8. Timeout -> TIMEOUT

G9. Successful response -> parser extracts generated text

Do not report "invalid API key" if the real cause is model access or quota.

---

## 14. Gemini API-key audit

If Gemini fails:

1. Verify the key is actually supplied to the backend.
2. Verify the key is not being overwritten by an empty environment variable.
3. Verify the project associated with the key.
4. Verify the key's restrictions.
5. Verify the selected model is accessible.
6. Capture sanitized HTTP status and provider response.
7. Check whether the failure is quota/rate-limit/billing related.
8. Test the same key outside BhoomiLens using the official SDK or documented REST request.

The external direct test is mandatory before declaring the BhoomiLens adapter broken.

---

# 15. Ollama standalone tests

Test Ollama without BhoomiLens.

### O1 — service

~~~
curl http://127.0.0.1:11434/api/tags
~~~

Expected: JSON with installed models.

### O2 — native chat

Use the native /api/chat endpoint with:

~~~
Reply exactly: OK
~~~

### O3 — OpenAI-compatible API

Test /v1/chat/completions only if the application uses this interface.

Compare native and OpenAI-compatible behavior.

---

# 16. Ollama performance benchmark

Run each installed model at least three times:

~~~
Run 1 = cold
Run 2 = warm
Run 3 = warm
~~~

Collect:

- model load time
- first-token latency
- total latency
- generated tokens
- tokens/sec
- CPU usage
- RAM
- GPU utilization
- VRAM
- prompt/context size

While generating, inspect:

~~~
ollama ps
nvidia-smi
~~~

Do not change models before collecting these measurements.

---

# 17. Ollama routing

Initial candidate roles:

~~~
qwen3:8b      -> primary text/reasoning
deepseek-r1:8b -> complex reasoning only
qwen3-vl:4b   -> vision/scanned documents
gemma3:4b     -> lightweight fallback
~~~

Do not load several large models concurrently unless necessary.

For the 6 GB GPU, benchmark whether qwen3:8b actually fits and runs efficiently. If it is CPU-bound or suffers heavy memory pressure, test qwen3-vl:4b/gemma3:4b for appropriate tasks.

---

# 18. Diagnose why Ollama is slow

Classify the result:

### GPU high + VRAM high
Likely GPU/memory bottleneck.

### GPU low + CPU high
Investigate GPU offload/runtime configuration.

### First request slow, later requests fast
Model cold-start/loading overhead.

### All requests slow
Model/runtime/context problem.

### Tiny prompt fast, BhoomiLens prompt slow
Application is sending too much context or duplicate text.

Measure prompt size before changing architecture.

---

# 19. Context audit

Search for:

~~~
messages
system_prompt
document_text
extracted_text
chat_history
max_tokens
context
~~~

Record actual input size for each provider.

Look for:

- duplicate OCR
- duplicate document pages
- entire chat history being resent
- irrelevant metadata
- huge JSON blobs
- unnecessary system prompts

Do not blame Ollama for application-generated context bloat.

---

# 20. Retry policy

Retry only transient conditions:

~~~
408
429
500
502
503
504
temporary connection reset/network failure
~~~

Maximum: **3 total attempts**.

Use exponential backoff with jitter and honor Retry-After when provided.

Do NOT retry:

~~~
400
401
403
404
invalid request
invalid model
unsupported feature
~~~

Never run infinite retry loops.

Do not repeatedly retry an invalid free API key.

---

# 21. Repeated diagnostic mode

The user wants to test providers repeatedly.

Create:

~~~
python backend/scripts/test_ai_connections.py --provider gemini --repeat 3
~~~

Allowed repeat range: 1 to 5.

Example:

~~~
Test 1/3: PASS 842 ms
Test 2/3: PASS 511 ms
Test 3/3: PASS 496 ms

Success rate: 100%
Median latency: 511 ms
~~~

If the first attempt produces a non-retryable authentication/model error, stop instead of wasting quota.

---

# 22. CLI commands

Support:

~~~
python backend/scripts/test_ai_connections.py --provider sarvam
python backend/scripts/test_ai_connections.py --provider gemini
python backend/scripts/test_ai_connections.py --provider ollama
python backend/scripts/test_ai_connections.py --provider all
python backend/scripts/test_ai_connections.py --provider ollama --model qwen3:8b
python backend/scripts/test_ai_connections.py --provider gemini --repeat 3
~~~

CLI output must contain:

- provider
- endpoint
- model
- attempt
- latency
- HTTP status
- normalized error
- sanitized provider message

Never print API keys.

---

# 23. Backend test endpoint

Keep/use:

~~~
POST /provider/test
~~~

For Sarvam/Gemini:

~~~
{
  "provider": "gemini",
  "model": "optional",
  "api_key": "runtime-only"
}
~~~

For Ollama:

~~~
{
  "provider": "ollama",
  "base_url": "http://127.0.0.1:11434",
  "model": "qwen3:8b"
}
~~~

Never persist the key.

Keep/use:

~~~
GET /ollama/models
~~~

This endpoint should dynamically query Ollama rather than hardcode model names.

---

# 24. Frontend provider status

Do not display only "Connected / Disconnected".

Use actionable states:

| State | Meaning |
|---|---|
| Not configured | No key/model |
| Testing | Request in progress |
| Connected | Minimal request succeeded |
| Model unavailable | Key works, selected model does not |
| Authentication failed | Key rejected |
| Rate limited | 429 |
| Quota exhausted | Free quota unavailable |
| Provider error | 5xx/other provider failure |
| Timeout | Request timed out |
| Local unavailable | Ollama unreachable |
| Local slow | Ollama works but benchmark is slow |

The UI should show the normalized diagnosis and latency.

---

# 25. Production adapter architecture

Production code should reuse the same adapters used by the test endpoint.

Target:

~~~
ProviderConnection
   |
   +-- test_connection()
   |
   +-- generate()
~~~

Avoid having one HTTP implementation for testing and a completely separate implementation for production.

This prevents the common situation where the "Test" button passes but the real BhoomiLens pipeline still fails.

---

# 26. Full pipeline only after standalone tests pass

Once provider tests pass:

~~~
Frontend
 -> /provider/test
 -> adapter
 -> provider
 -> normalized result
~~~

Then test:

~~~
/chat
/explain
/document extraction
/document reasoning
~~~

Run one small synthetic document first.

Measure:

1. upload
2. preprocessing
3. OCR
4. extraction
5. reasoning
6. number of provider calls
7. fallback calls
8. total latency
9. final response

---

# 27. Fallback rules

Fallback must be error-aware.

### Invalid API key
Do not repeatedly retry the same provider.

### Model unavailable
Try another configured provider/model.

### 429
Bounded retry, then fallback.

### Quota exhausted
Fallback to another configured provider.

### Ollama unavailable
Use external provider if configured.

### Ollama slow
Do not automatically call it multiple times.

---

# 28. Vision/OCR routing

For scanned land records:

~~~
PDF
 -> page rendering
 -> image preprocessing
 -> qwen3-vl:4b or external vision model
 -> structured extraction
 -> document-level reasoning
~~~

Do not send an entire multi-page high-resolution PDF as one huge prompt.

Page-level processing makes performance and failures easier to diagnose.

---

# 29. Security requirements

Never log:

- API keys
- Authorization headers
- uploaded document contents
- base64 images
- full private OCR text

Log only safe metadata:

~~~
provider
model
endpoint
latency
status
error code
file name
MIME type
file size
page count
~~~

If request/response debugging is needed, redact secrets and truncate document text.

---

# 30. Tests

Add unit tests for:

- credential validation
- key redaction
- retry classification
- error normalization
- model selection
- response parsing
- Ollama discovery
- timeout handling
- 401/403
- 429
- 5xx

Mock provider HTTP calls in normal CI.

Live tests must be opt-in:

~~~
RUN_LIVE_PROVIDER_TESTS=1 pytest backend/tests/provider_connections
~~~

Never run real API calls automatically in GitHub Actions because the keys may consume free-tier quota.

---

# 31. Reference implementations

Inspect these before implementing provider abstraction:

- Sarvam official Python SDK: sarvamai
- Google official Python SDK: google-genai
- PraisonAI: https://github.com/MervinPraison/PraisonAI
- OmniRoute: https://github.com/diegosouzapw/OmniRoute

Use them for architectural ideas only. Do not add unnecessary dependencies.

Official provider documentation remains the source of truth.

---

# 32. Execution sequence for Antigravity

## Step 1 — Audit
Inspect existing provider/frontend/backend code and report the current data flow.

## Step 2 — Normalize
Create provider result/error models and tests.

## Step 3 — Sarvam
Implement and run minimal standalone test with the user's real free key.

## Step 4 — Gemini
Implement and run minimal standalone test with the user's real free key and a currently accessible free-tier model.

## Step 5 — Ollama
Implement direct API test, model discovery, and 3-run performance benchmark.

## Step 6 — CLI
Add test_ai_connections.py with bounded repeat mode.

## Step 7 — Backend
Connect adapters to /provider/test and /ollama/models.

## Step 8 — Frontend
Connect Settings/Test buttons and actionable statuses.

## Step 9 — Production integration
Make /chat, /explain and document reasoning reuse the tested adapters.

## Step 10 — Full document test
Run representative mutation, khatoni, and sale-deed PDFs.

---

# 33. Verification commands

Use the repository's actual commands if they differ.

~~~
pytest
npm run lint
npm run build

ollama list
ollama ps
nvidia-smi
curl http://127.0.0.1:11434/api/tags

python backend/scripts/test_ai_connections.py --provider sarvam
python backend/scripts/test_ai_connections.py --provider gemini
python backend/scripts/test_ai_connections.py --provider ollama
~~~

Do not claim success from frontend build alone.

---

# 34. Required final diagnostic report

Antigravity must finish with:

~~~
PROVIDER CONNECTION REPORT
==========================

SARVAM
------
Key supplied: YES/NO
Authentication: PASS/FAIL
Model: <model>
Model access: PASS/FAIL
Minimal chat: PASS/FAIL
Latency: <ms>
Quota/rate limit: <status>
Final diagnosis: <one sentence>

GEMINI
------
Key supplied: YES/NO
Authentication: PASS/FAIL
Model: <model>
Model access: PASS/FAIL
Minimal generation: PASS/FAIL
Latency: <ms>
Quota/rate limit: <status>
Final diagnosis: <one sentence>

OLLAMA
------
Service: PASS/FAIL
Models discovered: <list>
Selected model: <model>
GPU detected: YES/NO
GPU utilization: <measurement>
VRAM: <measurement>
Cold latency: <ms>
Warm latency: <ms>
Tokens/sec: <measurement>
Final diagnosis: <one sentence>

BHOOMILENS
----------
Provider test endpoint: PASS/FAIL
Frontend test button: PASS/FAIL
Document pipeline: PASS/FAIL
Fallback: PASS/FAIL

ROOT CAUSE
----------
<exact root cause>

FIXES
-----
<files changed and why>

VERIFICATION
------------
<commands and results>
~~~

---

# 35. Definition of done

Do not mark this task complete merely because the UI displays "connected".

Done means:

~~~
direct provider request works
+
adapter works
+
backend test endpoint works
+
frontend test works
+
production request works
+
document pipeline works
+
failure states are accurate
+
free-tier constraints are respected
+
secrets are protected
+
Ollama performance is measured
~~~

The key outcome is **diagnostic certainty**. If Sarvam or Gemini still fails, BhoomiLens must clearly identify whether the cause is the key, project/account, free-tier quota, model access, request schema, network, provider service, or BhoomiLens code.
