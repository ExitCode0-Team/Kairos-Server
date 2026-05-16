# Kairos Server

Minimal **FastAPI** service for:

1. **CV extraction** — download PDFs from Supabase Storage (`cv-uploads`), extract text with PyMuPDF, fall back to **Tesseract OCR** for scans.
2. **User projects** — read/write `profiles.projects` JSON by `user_id`.

## System dependencies (OCR)

```bash
# Ubuntu / Debian
sudo apt-get install -y tesseract-ocr poppler-utils

# macOS
brew install tesseract poppler
```

## Setup

```bash
cd kairos-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with SUPABASE_URL and SUPABASE_SERVICE_KEY
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for Swagger UI.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| POST | `/api/v1/extract` | Download PDF + return text |
| PUT | `/api/v1/users/{user_id}/projects` | Save projects JSON |
| GET | `/api/v1/users/{user_id}/projects` | Read projects JSON |

If `API_SECRET` is set in `.env`, send header: `X-API-Secret: <value>`.

### Extract example

```bash
curl -X POST http://localhost:8000/api/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"upload_id": "YOUR_CV_UPLOAD_UUID"}'
```

### Projects example

```bash
curl -X PUT http://localhost:8000/api/v1/users/USER_UUID/projects \
  -H "Content-Type: application/json" \
  -d '{"projects": [{"name": "Demo", "role": "Engineer"}]}'
```
