# Cloud Deployment Guide (Provider-Agnostic)

This guide applies to free or paid providers that run Docker containers.

For a complete Azure + GoDaddy + GitHub Actions rollout, see:
- `docs/AZURE_PRODUCTION_SETUP.md`

## Supported Deployment Patterns

## 1) Split Services (Recommended)
- Deploy `backend` and `frontend` as separate container services.
- Use managed PostgreSQL (`DATABASE_URL_OVERRIDE`).
- Optionally use S3-compatible storage by setting `STORAGE_BACKEND=s3`.

## 2) Same-Domain via Reverse Proxy
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
  - or `/api/v1` when same-domain reverse proxy is used

## Runtime Port Compatibility
- Backend container reads `PORT` (defaults to `8000`).
- Frontend container reads `PORT` (defaults to `3000`).
- Most cloud providers inject `PORT` automatically.

## Performance and Reliability
- Use managed PostgreSQL with connection pooling enabled.
- Keep health probes enabled:
  - backend: `/health/live`, `/health/ready`
  - frontend: `/`
- Scale horizontally at service level.
- Keep CDN/static caching enabled in front of frontend where available.

## Security Baseline
- Never commit real secrets in `.env` files.
- Enforce HTTPS end-to-end.
- Set strict `CORS_ORIGINS` and `TRUSTED_HOSTS`.
- Keep docs disabled in production (`ENABLE_DOCS=false`).
- Configure webhook secrets (`RAZORPAY_WEBHOOK_SECRET`) and verify signatures server-side.

## Compose Options
- Local full stack with bundled DB:
  - `docker compose --env-file .env up -d --build`
- Cloud mode with managed DB:
  - `docker compose -f docker-compose.cloud.yml --env-file .env up -d --build`
