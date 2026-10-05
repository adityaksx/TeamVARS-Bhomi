# BhoomiLens

AI-assisted land-record reconciliation for PS41.

BhoomiLens turns RTC, mutation, sale deed, EC and supporting property records into structured evidence, reconciles them across documents, flags contradictions, and explains findings without pretending to establish legal title.

## Architecture

```
Next.js light/editorial UI
        |
      FastAPI
        |
  +-----+----------------------+
  |                            |
Sarvam Document AI       AI Provider layer
  |                       /         \
Extract + sources      Sarvam      OpenModel
  |                       \         /
  +----------> deterministic reconciliation
                         |
                 evidence + findings
```

## Providers

- **Sarvam AI** — sarvam-105b for reasoning and /doc-ai/v1/job/extract for structured document extraction.
- **OpenModel** — configurable model through the OpenModel proxy.
- **Local Demo** — zero-key deterministic provider for UI/demo testing.

OpenModel pricing and model availability are account/config dependent; configure OPENMODEL_MODEL explicitly rather than hard-coding a claim that a model is universally free.

## Run

### Backend

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

Open http://localhost:3000.

### Environment

```env
AI_PROVIDER=mock
SARVAM_API_KEY=
SARVAM_MODEL=sarvam-105b
OPENMODEL_API_KEY=
OPENMODEL_MODEL=
```

API keys stay server-side.

## Trust boundary

BhoomiLens is an AI-assisted document screening/reconciliation system. It does not establish legal title, ownership, absence of litigation, or fraud.
