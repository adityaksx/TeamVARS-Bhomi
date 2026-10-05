# BhoomiLens

AI-assisted **Uttar Pradesh land-record reconciliation** for PS41.

BhoomiLens turns **Khatauni, Gata/Khasra, Mutation/Namantaran, Sale Deed, EC/litigation and supporting property records** into structured evidence, reconciles them across documents, flags contradictions, and explains findings without pretending to establish legal title.

## Current implementation

```
Browser
  |
  v
Next.js light/editorial console — UP-first
  |
  v
FastAPI
  |
  +--> case store (local JSON or optional PostgreSQL)
  +--> document storage
  +--> Sarvam Document AI (when configured)
  +--> AI provider for explanations
            |--> Sarvam 105B
            |--> OpenModel
            `--> Local demo
  |
  v
normalization -> entity matching -> deterministic reconciliation
  |
  v
findings + source-page evidence + consistency score
```

The reconciliation engine is intentionally deterministic. AI is used for semantic explanation and ambiguous identity resolution, not for making legal conclusions.

## Providers

- **Sarvam AI** — `sarvam-105b` for reasoning and Sarvam Document AI `/doc-ai/v1/job/extract` for structured document extraction.
- **OpenModel** — configurable model through `https://api.openmodel.ai`, using its Anthropic-compatible Messages protocol.
- **Local Demo** — zero-key deterministic provider for UI and reconciliation testing.

Sarvam currently gives new users ₹100 of signup credits across its APIs. OpenModel supports free models only when its current model price multiplier is 0; the model catalog and pricing are dynamic, so the repository does not hard-code a supposedly-free model. Configure `OPENMODEL_MODEL` from the current OpenModel catalog. 

## Real analysis flow

1. Create a case.
2. Upload multiple PDF/PNG/JPEG documents.
3. Persist document metadata and files.
4. Submit each PDF to Sarvam Document AI when a Sarvam key is configured.
5. Split PDFs into <=10-page chunks before extraction.
6. Merge structured extraction results and preserve source-page offsets.
7. Map UP terminology into the canonical schema and normalize owner names, Gata/Khasra identifiers, locations, dates and land extent.
8. Render uploaded PDF pages and deterministically anchor extracted evidence to matching text regions when text is available.
9. Reconcile owners, Gata/Khasra identifiers, extents and mutation coverage with deterministic rules.
10. Compute a Record Consistency Score.
11. Ask Sarvam/OpenModel to explain a finding using the stored evidence.

Without a Sarvam key, the analysis pipeline uses filename-based fixtures so the full UI/reconciliation workflow remains testable without external API usage.

## Run

### Backend

Python 3.10–3.14 is supported. The dependency set uses a Python-3.14-compatible Pydantic release.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`.

### Environment

```env
AI_PROVIDER=mock

SARVAM_API_KEY=
SARVAM_MODEL=sarvam-105b
SARVAM_DIGITISE_ENABLED=false
SARVAM_DOCUMENT_LANGUAGE=hi-IN

OPENMODEL_API_KEY=
OPENMODEL_MODEL=
OPENMODEL_BASE_URL=https://api.openmodel.ai

CASE_STORE_BACKEND=local
DATABASE_URL=
```

API keys stay server-side.

Set `SARVAM_DIGITISE_ENABLED=true` to enable the optional Digitise pass.

Set `CASE_STORE_BACKEND=postgres` and `DATABASE_URL` to use PostgreSQL for case/analysis/document metadata.

### Durable document storage

Local file storage is the default for development. For multi-instance production deployments, set `DOCUMENT_STORAGE_BACKEND=s3` and configure the S3-compatible bucket credentials below. Cloudflare R2, AWS S3 and other S3-compatible stores are supported through the same adapter.

```env
DOCUMENT_STORAGE_BACKEND=s3
DOCUMENT_STORAGE_BUCKET=bhoomilens-documents
DOCUMENT_STORAGE_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
DOCUMENT_STORAGE_REGION=auto
DOCUMENT_STORAGE_ACCESS_KEY=<server-side-key>
DOCUMENT_STORAGE_SECRET_KEY=<server-side-secret>
```

The database stores an object reference such as `s3://bucket/cases/<case>/documents/<document>/<filename>`; analysis temporarily materializes remote files only when PDF parsing or source rendering needs a filesystem path.

Uploads are validated by file signature rather than trusting only the browser MIME type. The API also enforces a 25 MB default per-document limit, a 100 MB per-case aggregate limit, and 20 documents per case; these are configurable through the `MAX_*` settings. Filenames are path-normalized before storage.

Digitise uses the current `/doc-ai/v1/job/digitise` endpoint and JSON page blocks with bounding boxes.

## Testing

Backend tests cover:

- name normalization
- UP Gata/Khasra normalization
- UP document-type mapping
- survey/Gata mismatch detection
- extent mismatch detection
- mutation-gap detection
- evidence page propagation
- visual PDF text anchors
- Sarvam Digitise bounding-box anchors
- structured PDF report generation
- ambiguous entity matching

CI runs Python compilation/unit tests and Next.js typecheck/build.

## Trust boundary

BhoomiLens is an AI-assisted document screening/reconciliation system. It does not establish legal title, ownership, absence of litigation, or fraud.
