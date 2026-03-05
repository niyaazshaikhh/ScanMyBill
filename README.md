# ScanMyBill

AI-powered billing and GST workflow platform specially made for Indian MSMEs.

## Tech Stack
- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS
- Backend: FastAPI, SQLAlchemy, JWT auth, Google OAuth login
- Database: PostgreSQL
- AI/Document Processing: OpenAI/Azure OpenAI, Tesseract OCR fallback, PDF/image parsers
- Payments: Razorpay subscriptions
- DevOps: Docker + Docker Compose

## Core Capabilities
- AI-assisted bill extraction and invoice creation from PDF/image uploads
- GST analytics dashboard with period filters and trend views
- Sales/Purchase invoice management with folder-style exports
- Non-GST delivery challan workflows
- Client analytics and reusable HSN/SAC master list
- Subscription-based access control (Standard/Pro/Business)
- Newsletter subscriptions and admin broadcast tooling
- Security hardening: rate limiting, cookie/session controls, trusted hosts, production guards

## Project Structure
```text
ScanMyBill_IN/
  backend/
    app/
      api/v1/endpoints/
      core/
      models/
      schemas/
      services/
      utils/
    requirements.txt
    Dockerfile
    .env.example
  frontend/
    app/
    components/
    lib/
    Dockerfile
    .env.example
  docs/
    API.md
    DATABASE_SCHEMA.md
    ERD.md
  docker-compose.yml
  .env.example
```

## Environment Setup

1. Root env (Docker Compose level)
```bash
cp .env.example .env
```

2. Backend env
```bash
cp backend/.env.example backend/.env
```

3. Frontend env
```bash
cp frontend/.env.example frontend/.env
```

## Local Development (without Docker)

### Prerequisites
- Node.js 20+
- Python 3.11+
- PostgreSQL 14+
- Tesseract OCR + Poppler utilities (for fallback OCR and scanned PDFs)

### Backend
```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open:
- Frontend: `http://localhost:3000`
- API: `http://localhost:8000/api/v1`
- Health: `http://localhost:8000/health`

## Docker Compose

```bash
docker compose --env-file .env up -d --build
```

Default mapped ports:
- Frontend: `http://localhost:${FRONTEND_PORT:-3000}`
- Backend: `http://localhost:${BACKEND_PORT:-8000}`

Notes:
- Frontend waits for backend health.
- Backend waits for PostgreSQL health.
- Uploaded files are persisted in the `backend_uploads` Docker volume.

## Production Checklist

Set strong values before deploying:
- `POSTGRES_PASSWORD`
- `SECRET_KEY` (in `backend/.env`, 32+ chars)
- `ENVIRONMENT=production`
- `COOKIE_SECURE=true`
- `ENFORCE_HTTPS=true`
- `CORS_ORIGINS` and `TRUSTED_HOSTS` with exact production domains
- `SEED_DEFAULT_ADMIN=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=false`
- `RAZORPAY_*`, `SMTP_*`, and AI provider keys (`OPENAI_*` / `AZURE_OPENAI_*`) as needed

## Documentation
- API summary: `docs/API.md`
- Database schema: `docs/DATABASE_SCHEMA.md`
- ERD description: `docs/ERD.md`

## Important Notes
- API docs (`/docs`) are disabled when `ENVIRONMENT=production` and `ENABLE_DOCS=false`.
- This project currently uses SQLAlchemy `create_all` style startup migrations.
- Add Alembic migrations before strict production rollout.
