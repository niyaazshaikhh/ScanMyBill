# Security and Deployment Hardening

Last updated: April 23, 2026

This backend includes baseline hardening suitable for production once secrets and host policies are configured correctly.

## Implemented Security Controls

- Centralized API error envelope with stable error codes.
- Request ID propagation (`X-Request-ID`) and structured request logging.
- Startup production guardrails (`ENVIRONMENT=production`) that block unsafe configuration.
- Trusted host middleware (`TRUSTED_HOSTS`) and HTTPS redirect support (`ENFORCE_HTTPS`).
- Proxy header support when running behind ingress (`TRUST_PROXY_HEADERS=true`).
- Security response headers:
  - `Content-Security-Policy`
  - `X-Frame-Options`
  - `X-XSS-Protection`
  - `X-Content-Type-Options`
  - `Strict-Transport-Security` (prod/HTTPS)
- Endpoint-aware rate limiting for auth, general traffic, and invoice PDF flows.
- Login brute-force protection and account lockout windows.
- Cookie/session hardening (`COOKIE_SECURE`, `COOKIE_SAMESITE`, inactivity timeout).
- Upload security checks (MIME + extension + size limits + defensive parsing).
- PostgreSQL hardening (pooling, connect timeout, statement timeout).
- Razorpay verification hardening (server-side verify + webhook signature checks).

## Production Startup Checks

When `ENVIRONMENT=production`, startup fails if any of these are unsafe:

- Weak/default `SECRET_KEY`
- `DEBUG=true`
- `ENABLE_DOCS=true`
- `COOKIE_SECURE=false`
- `ENFORCE_HTTPS=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=true`
- Wildcard CORS origin (`*`)
- Missing `CORS_ORIGINS` or `TRUSTED_HOSTS`
- Localhost or loopback values in `CORS_ORIGINS` or `TRUSTED_HOSTS`
- `SEED_DEFAULT_ADMIN=true`
- Weak/default DB password (unless `DATABASE_URL_OVERRIDE` is provided)

## Required Production Environment Variables

Set these values in your runtime secret manager or environment:

- `ENVIRONMENT=production`
- `SECRET_KEY` (32+ random characters)
- `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- or `DATABASE_URL_OVERRIDE` for managed DB
- `COOKIE_SECURE=true`
- `ENFORCE_HTTPS=true`
- `CORS_ORIGINS` with exact frontend domain(s)
- `TRUSTED_HOSTS` with exact hostnames
- `SEED_DEFAULT_ADMIN=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=false`
- `SMTP_*` for password reset/newsletter flows
- `RAZORPAY_*` for payment flows
- `OPENAI_*` and/or `AZURE_OPENAI_*` for AI extraction

## Docker Compose Notes

Root `docker-compose.yml` includes:

- DB health checks before backend startup
- Backend health checks before frontend startup
- Dedicated uploads volume (`backend_uploads`)

Run:

```bash
docker compose --env-file .env up -d --build
```

## Operational Recommendations

- Keep secrets in a managed secret store, not tracked files.
- Restrict DB and backend ingress using NSGs/firewalls.
- Terminate TLS at the edge and preserve forwarded proto headers.
- Monitor `/health/live` and `/health/ready`.
- Add centralized logs and alerting on 5xx and auth spikes.
- Introduce Alembic migrations for controlled schema evolution.
