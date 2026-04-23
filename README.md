# ScanMyBill

Last updated: April 23, 2026

AI-powered billing and GST workflow platform built for Indian MSMEs.

## Tech Stack
- Frontend: Next.js 14 (App Router), TypeScript, Tailwind CSS
- Backend: FastAPI, SQLAlchemy, JWT auth, Google OAuth
- Database: PostgreSQL
- AI and document processing: OpenAI or Azure OpenAI, Tesseract OCR fallback, PDF/image parsing
- Payments: Razorpay (order-based checkout with signature verification)
- DevOps: Docker, Docker Compose, GitHub Actions, Azure Container Apps

## Core Capabilities
- AI-assisted bill extraction and invoice creation from PDF/image uploads
- GST analytics dashboard with period filters, trend views, and assistant summaries
- Sales and purchase invoice management with folder-style export
- Non-GST delivery challan workflows
- Client analytics and reusable HSN/SAC master list
- Subscription-based access control (`FREE`, `STANDARD`, `PRO`, `BUSINESS`)
- Newsletter subscriptions and admin broadcast tooling
- Undo flow for selected destructive actions via in-app notifications
- Security guardrails: rate limiting, cookie/session hardening, trusted hosts, production checks

## Project Structure
```text
ScanMyBill/
  backend/
    app/
      api/v1/endpoints/
      core/
      models/
      schemas/
      services/
      utils/
    tests/
    SECURITY_DEPLOYMENT.md
    requirements.txt
    Dockerfile
    .env.example
  frontend/
    app/
    components/
    lib/
    docs/
    Dockerfile
    .env.example
  docs/
    API.md
    DATABASE_SCHEMA.md
    ERD.md
    CLOUD_DEPLOYMENT.md
    AZURE_PRODUCTION_SETUP.md
  docker-compose.yml
  docker-compose.cloud.yml
  .env.example
```

## Environment Setup

Do not commit populated env files. Keep `.env`, `backend/.env`, and `frontend/.env` local-only.

1. Root env (Compose level)
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

## Environment Profiles

Use separate values for local and production:

- Local profile (`.env`)
  - `ENVIRONMENT=development`
  - `ENABLE_DOCS=true`
  - `COOKIE_SECURE=false`
  - `ENFORCE_HTTPS=false`
  - `NEXT_PUBLIC_APP_URL=http://localhost:3000`
  - `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`
- Production profile (GitHub variables plus cloud runtime env)
  - `NEXT_PUBLIC_APP_URL=https://app.yourdomain.com`
  - `NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1` (or `/api/v1` with reverse proxy)
  - `CORS_ORIGINS=https://app.yourdomain.com`
  - `TRUSTED_HOSTS=api.yourdomain.com,app.yourdomain.com`
  - `COOKIE_SECURE=true`
  - `ENFORCE_HTTPS=true`

## Local Development (Without Docker)

### Prerequisites
- Node.js 20+
- Python 3.11+
- PostgreSQL 14+
- Tesseract OCR and Poppler utilities (fallback OCR + scanned PDFs)

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
- Health: `http://localhost:8000/health/live`

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
- Uploads persist in the `backend_uploads` Docker volume.

## Cloud Compatibility (Provider-Agnostic)

The project is container-first and cloud-portable:
- Backend supports managed DB via `DATABASE_URL_OVERRIDE`.
- Backend and frontend support runtime `PORT` env.
- Frontend supports `NEXT_PUBLIC_API_URL=/api/v1` for same-domain reverse proxy setup.
- Frontend uses Next.js standalone runtime for leaner deployments.

Managed DB Compose mode:

```bash
docker compose -f docker-compose.cloud.yml --env-file .env up -d --build
```

Required:
- `DATABASE_URL_OVERRIDE`
- `CORS_ORIGINS`
- `TRUSTED_HOSTS`

## CI/CD

GitHub Actions workflows:
- `ci.yml`: backend tests + frontend lint/build + Docker build validation
- `deploy.yml`: OIDC-based deployment to Azure Container Apps on `main` and manual dispatch

Pipeline behavior:
- Push to `develop` or PR: CI checks only
- Push to `main`: CI + production deploy
- Deploy workflow rejects production URL variables that still point to `localhost` or non-HTTPS values

Production pipeline setup details:
- `docs/AZURE_PRODUCTION_SETUP.md`

## GitHub Publication

Before making the repository public:

- Keep only example env files in git. Never commit `.env`, `backend/.env`, or `frontend/.env`.
- Replace placeholder values in `github-env.json` and `github-oidc.json` before creating federated credentials.
- Store secrets in GitHub Secrets or your cloud secret manager, not in tracked files.
- If a real secret was ever committed or pushed, rotate it and rewrite git history before publishing.
- Review the publication checklist in `docs/GITHUB_PUBLISHING.md`.

## Production Checklist

Set strong values before deploying:
- `POSTGRES_PASSWORD`
- `SECRET_KEY` (32+ chars)
- `ENVIRONMENT=production`
- `COOKIE_SECURE=true`
- `ENFORCE_HTTPS=true`
- `CORS_ORIGINS` and `TRUSTED_HOSTS` set to exact production domains
- `SEED_DEFAULT_ADMIN=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=false`
- `RAZORPAY_*`, `SMTP_*`, and AI keys (`OPENAI_*` or `AZURE_OPENAI_*`) as needed

## Production Payment Flow

1. Frontend calls `POST /api/v1/payments/orders`
2. Backend creates Razorpay order
3. Frontend opens Razorpay checkout
4. User completes payment
5. Frontend posts signature payload to `POST /api/v1/payments/verify`
6. Backend verifies signature and updates `payment_events`

## Documentation
- API summary: `docs/API.md`
- Database schema: `docs/DATABASE_SCHEMA.md`
- ERD description: `docs/ERD.md`
- Cloud deployment guide: `docs/CLOUD_DEPLOYMENT.md`
- Azure production rollout: `docs/AZURE_PRODUCTION_SETUP.md`
- GitHub publication checklist: `docs/GITHUB_PUBLISHING.md`
- Backend security hardening: `backend/SECURITY_DEPLOYMENT.md`

## Important Notes
- API docs (`/docs`) are disabled when `ENVIRONMENT=production` and `ENABLE_DOCS=false`.
- The backend currently uses SQLAlchemy `create_all` + runtime guards for schema alignment.
- Add Alembic migrations before strict long-term production rollout.
