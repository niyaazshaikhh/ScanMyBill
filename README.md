# ScanMyBill.in

Production-oriented full-stack SaaS starter for OCR-powered bill processing, GST analytics, and invoice automation.

## Tech Stack
- Frontend: Next.js 14 (App Router), Tailwind CSS, ShadCN-style UI, Recharts, pdf-lib
- Backend: FastAPI, SQLAlchemy, JWT auth, Google OAuth token login, Tesseract OCR
- Database: PostgreSQL
- Storage: Local (default) with S3-ready abstraction
- Payments: Razorpay subscription demo endpoint + frontend checkout integration
- DevOps: Docker + Docker Compose

## Core Features Implemented
- Landing page (SSR) with interactive draggable bill hero and SEO metadata
- Dashboard (`/dashboard`) with KPI cards + line/pie charts + period filters
- Invoices (`/invoices`) with folder-style period/type filtering + combined PDF export
- Clients (`/clients`) with analytics and add-client flow
- Create (`/create`) invoice builder with PDF export and DB upload
- OCR bill upload flow (`/dashboard` upload widget + backend `/bills/upload`)
- Auth (JWT, Google OAuth ID token flow), protected routes, role model (`admin`, `user`)
- Sitemap generation (`/sitemap.xml`)

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
      main.py
    requirements.txt
    Dockerfile
    .env.example
  frontend/
    app/
      (auth)/signin
      (auth)/signup
      (app)/dashboard
      (app)/invoices
      (app)/clients
      (app)/create
      (app)/settings
      layout.tsx
      page.tsx
      sitemap.ts
    components/
    lib/
    middleware.ts
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

### 1. Root env (for Docker Compose)
```bash
cp .env.example .env
```

### 2. Backend env
```bash
cp backend/.env.example backend/.env
```

### 3. Frontend env
```bash
cp frontend/.env.example frontend/.env
```

## Local Development (without Docker)

## Prerequisites
- Node.js 20+
- Python 3.11+
- PostgreSQL 14+
- Tesseract OCR installed and available in PATH
- Poppler utilities installed (for scanned PDF OCR)

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
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Docker Setup

```bash
# from repository root
docker compose --env-file .env up --build
```

Services:
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- PostgreSQL: `localhost:5432`

## Authentication and Security
- JWT bearer auth for protected backend endpoints
- Google OAuth login via verified ID token (`/auth/google`)
- Route protection in Next.js middleware (`/dashboard`, `/invoices`, `/clients`, `/create`, `/settings`)
- Role model (`admin`, `user`) stored in JWT and user record
- Upload validation for MIME type and file size

## Storage Architecture
- `STORAGE_BACKEND=local` (default): files stored in `backend/uploads`
- `STORAGE_BACKEND=s3`: uses S3 implementation in `app/core/storage.py`
- OCR pipeline works directly on local files or downloaded temporary files for S3 mode

## Payment Demo (Razorpay)
Set in `backend/.env` and `frontend/.env`:
- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_PLAN_ID`
- `NEXT_PUBLIC_RAZORPAY_KEY_ID`

If keys are missing, backend returns a mock subscription ID for safe demo flow.

## SEO
- Metadata configured in `frontend/app/layout.tsx`
- Sitemap generated at `frontend/app/sitemap.ts` -> `/sitemap.xml`
- Robots rules generated at `frontend/app/robots.ts`

## Database and API Docs
- Database schema: `docs/DATABASE_SCHEMA.md`
- ER diagram description: `docs/ERD.md`
- API documentation summary: `docs/API.md`
- Live OpenAPI docs: `/docs`

## Notes
- This starter uses SQLAlchemy `create_all` on startup for quick bootstrap.
- For strict production migration workflow, add Alembic migrations before go-live.