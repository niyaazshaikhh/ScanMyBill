# Cloud Deployment Guide (Provider-Agnostic)

Last updated: March 26, 2026

This guide applies to providers that run Docker containers.

For a complete Azure + GoDaddy + GitHub Actions rollout, see:
- `docs/AZURE_PRODUCTION_SETUP.md`

## Supported Deployment Patterns

### 1) Split Services (Recommended)
- Deploy `backend` and `frontend` as separate container services.
- Use managed PostgreSQL via `DATABASE_URL_OVERRIDE`.
- Optionally use S3-compatible storage by setting `STORAGE_BACKEND=s3`.

### 2) Same-Domain Reverse Proxy
- Route `/api/v1` to backend.
- Route `/` to frontend.
- Set `NEXT_PUBLIC_API_URL=/api/v1`.

## Required Environment Variables

### Backend (minimum production)
- `ENVIRONMENT=production`
- `SECRET_KEY` (32+ random chars)
- `DATABASE_URL_OVERRIDE=postgresql+psycopg2://...`
- `CORS_ORIGINS=https://your-frontend-domain`
- `TRUSTED_HOSTS=your-backend-domain,your-frontend-domain`
- `COOKIE_SECURE=true`
- `ENFORCE_HTTPS=true`
- `SEED_DEFAULT_ADMIN=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=false`

### Frontend (minimum production)
- `NEXT_PUBLIC_APP_URL=https://your-frontend-domain`
- `NEXT_PUBLIC_API_URL=https://your-backend-domain/api/v1`
- Use `NEXT_PUBLIC_API_URL=/api/v1` for same-domain reverse proxy deployments

## Runtime Port Compatibility
- Backend reads `PORT` (default `8000`).
- Frontend reads `PORT` (default `3000`).
- Most cloud providers inject `PORT` automatically.

## Health, Scale, and Reliability
- Use managed PostgreSQL with pooling enabled.
- Keep health probes enabled:
  - backend: `/health/live`, `/health/ready`
  - frontend: `/`
- Scale services horizontally based on CPU and request volume.
- Keep CDN and static caching enabled in front of frontend where available.

## Security Baseline
- Never commit real secrets in `.env` files.
- Enforce HTTPS end-to-end.
- Keep `CORS_ORIGINS` and `TRUSTED_HOSTS` strict.
- Keep docs disabled in production (`ENABLE_DOCS=false`).
- Configure webhook secrets (`RAZORPAY_WEBHOOK_SECRET`) and verify signatures server-side.

## Compose Options
- Local full stack with bundled DB:
  - `docker compose --env-file .env up -d --build`
- Cloud mode with managed DB:
  - `docker compose -f docker-compose.cloud.yml --env-file .env up -d --build`
