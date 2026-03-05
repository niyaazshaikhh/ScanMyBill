# Security and Deployment Hardening (Azure-Ready)

## Implemented protections

- Centralized error handling with a uniform API error schema:
  - `{"success": false, "error": {"code": "...", "message": "..."}}`
- Request context + request ID propagation (`X-Request-ID`).
- Structured request logging:
  - timestamp, request_id, user_id, endpoint, method, status_code, execution_time_ms
- Production security checks at startup:
  - disallow weak/default secrets, wildcard CORS, insecure cookies, docs/debug in production
- Security headers middleware:
  - `Content-Security-Policy`
  - `X-Frame-Options`
  - `X-XSS-Protection`
  - `X-Content-Type-Options`
  - `Strict-Transport-Security` (when HTTPS/prod)
- Rate limiting policies:
  - login: configurable (`RATE_LIMIT_LOGIN_PER_MINUTE`, default `5`)
  - auth endpoints: configurable (`RATE_LIMIT_AUTH_PER_MINUTE`, default `10`)
  - general endpoints: configurable (`RATE_LIMIT_DEFAULT_PER_MINUTE`, default `100`)
- Login brute-force protection:
  - failed-attempt counters per user
  - temporary account lockout after configurable threshold
- Strong password policy:
  - min/max length + uppercase + lowercase + number + special character
- File upload hardening:
  - allowed: PDF/PNG/JPG/JPEG only
  - extension + MIME signature validation
  - image/PDF metadata integrity checks
  - UUID-based persisted filename handled by storage layer
- Database hardening:
  - connection pooling + pre-ping
  - connection timeout + statement timeout for PostgreSQL
  - automatic rollback on session failure in dependency
- Razorpay hardening:
  - webhook signature verification
  - server-side payment fetch and status verification on `/payments/verify`
  - subscription/payment mismatch checks
- Health endpoints:
  - `/health/live` for liveness
  - `/health/ready` for DB readiness

## Azure deployment checklist

Set these in Azure App Settings / Key Vault references:

- `ENVIRONMENT=production`
- `SECRET_KEY` (32+ chars, random)
- `POSTGRES_*` or `DATABASE_URL_OVERRIDE`
- `COOKIE_SECURE=true`
- `ENFORCE_HTTPS=true`
- `CORS_ORIGINS` with exact domains only
- `TRUSTED_HOSTS` with your production hosts
- `SEED_DEFAULT_ADMIN=false`
- `EXPOSE_PASSWORD_RESET_TOKEN=false`
- SMTP credentials (`SMTP_*`)
- Razorpay credentials (`RAZORPAY_*`)
- Azure/OpenAI keys (`AZURE_OPENAI_*` / `OPENAI_*`) if used
- Optional Key Vault URI: `AZURE_KEY_VAULT_URI`

## Notes

- Keep `DEBUG=false` and `ENABLE_DOCS=false` in production.
- Do not log secrets/tokens/passwords.
- Restrict network access for DB and external services with NSGs/firewalls.
- Enable TLS end-to-end (Azure Front Door / App Gateway / HTTPS redirect).
