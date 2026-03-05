# Security and Deployment Hardening

This backend includes baseline hardening suitable for production deployment once secrets and host policies are configured correctly.

## Implemented Security Controls

- Centralized API error envelope with stable error codes.
- Request ID propagation (`X-Request-ID`) and structured request logging.
- Startup-time production guardrails (`ENVIRONMENT=production`) that block unsafe configuration.
- Trusted host middleware (`TRUSTED_HOSTS`) and HTTPS redirect support (`ENFORCE_HTTPS`).
- Security response headers:
  - `Content-Security-Policy`
  - `X-Frame-Options`
  - `X-XSS-Protection`
  - `X-Content-Type-Options`
  - `Strict-Transport-Security` (when HTTPS/prod)
- Endpoint-aware rate limiting for login/auth/general/invoice PDF traffic.
- Login brute-force protection and account lockout windows.
- Cookie/session hardening controls (`COOKIE_SECURE`, `COOKIE_SAMESITE`, inactivity timeout).
- Upload security checks (MIME + extension + size limits + defensive parsing).
- PostgreSQL connection hardening (pooling, connect timeout, statement timeout).
- Razorpay verification hardening (server-side verification and webhook signature checks).

## Production Startup Checks Enforced by the App

When `ENVIRONMENT=production`, startup fails if any of these are unsafe:

- Weak/default `SECRET_KEY`.
- `DEBUG=true`.
- `ENABLE_DOCS=true`.
- `COOKIE_SECURE=false`.
- `EXPOSE_PASSWORD_RESET_TOKEN=true`.
- Wildcard CORS origin (`*`).
- `SEED_DEFAULT_ADMIN=true`.
- Weak/default database password.
- `ENFORCE_HTTPS=false`.

## Required Environment Variables for Production

Set these values in your runtime secret manager or environment:

- `ENVIRONMENT=production`
- `SECRET_KEY` (32+ random characters)
- `POSTGRES_SERVER`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
  - or `DATABASE_URL_OVERRIDE`
- `COOKIE_SECURE=true`
- `ENFORCE_HTTPS=true`
- `CORS_ORIGINS` with exact frontend domain(s)
- `TRUSTED_HOSTS` with exact hostnames
- `SEED_DEFAULT_ADMIN=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=false`
- `SMTP_*` values for password reset/newsletter email flows
- `RAZORPAY_*` values for subscription workflows
- AI provider keys (`OPENAI_*` and/or `AZURE_OPENAI_*`) when AI extraction is enabled

## Docker Compose Notes

The root `docker-compose.yml` includes:

- DB health checks before backend startup.
- Backend health checks before frontend startup.
- Dedicated uploads volume (`backend_uploads`).

Use:

```bash
docker compose --env-file .env up -d --build
```

## Operational Recommendations

- Store secrets in a managed secret store, not in tracked files.
- Restrict DB and backend ingress using network security groups/firewalls.
- Terminate TLS at the edge and preserve forwarded proto headers.
- Monitor `/health/live` and `/health/ready`.
- Add centralized log aggregation and alerting on 5xx/error spikes.
- Introduce Alembic migrations for controlled schema evolution.
