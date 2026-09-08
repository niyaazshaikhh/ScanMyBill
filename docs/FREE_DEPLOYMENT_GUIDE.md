# ScanMyBill Free Demo Deployment Guide

Last updated: August 18, 2026

This guide explains how to deploy ScanMyBill using initially free/demo-friendly services:

- Frontend: Vercel Hobby, Next.js
- Backend: Render Free Web Service, Docker, FastAPI
- Database: Supabase Free PostgreSQL, Session Pooler
- Uploads: temporary local backend storage for MVP only

This setup is good for demos and early testing. It is not a final production architecture for paying users because free services can sleep, limits can change, and Render Free local files are not persistent.

## Architecture

```text
User browser
  |
  v
Vercel
Next.js frontend
  |
  | HTTPS API calls
  v
Render
FastAPI backend
  |
  | PostgreSQL Session Pooler
  v
Supabase
PostgreSQL database
```

Later, move permanent invoice files to Supabase Storage or S3-compatible storage:

```text
FastAPI backend
  |
  v
Supabase Storage / S3-compatible object storage
```

## Important Security Rules

Never commit or paste real secrets:

- `.env`
- `backend/.env`
- `frontend/.env`
- `DATABASE_URL_OVERRIDE`
- Supabase database password
- `SECRET_KEY`
- OpenAI or Azure OpenAI keys
- Razorpay secrets
- SMTP passwords
- OAuth secrets

Use `.env.example` files as templates only. Store real values in Render, Vercel, Supabase, or another secret manager.

If a real database password or connection string was ever shown in a screenshot, chat, commit, or log, rotate it.

## Prerequisites

You need:

- A GitHub repository containing this project
- A Vercel account
- A Render account
- A Supabase account
- Optional: Google Cloud OAuth client
- Optional: Razorpay account
- Optional: OpenAI or Azure OpenAI key
- Optional: SMTP provider

Repository layout:

```text
ScanMyBill/
  backend/
    app/
    requirements.txt
    Dockerfile
    .env.example
  frontend/
    app/
    middleware.ts
    next.config.mjs
    package.json
    .env.example
  docs/
  docker-compose.yml
  docker-compose.cloud.yml
  .env.example
```

## Step 1: Prepare GitHub Safely

Before deploying, make sure secrets are not tracked:

```bash
git ls-files .env
git ls-files backend/.env
git ls-files frontend/.env
```

Each command should produce no output.

Also check ignored files:

```bash
git status --ignored --short
```

Expected local-only files include:

```text
!! .env
!! backend/.env
!! frontend/.env
!! frontend/.next/
!! frontend/node_modules/
!! backend/uploads/
```

Push the latest safe code to GitHub:

```bash
git status
git push origin main
```

## Step 2: Create Supabase PostgreSQL

Create a Supabase project.

Recommended region for this setup:

```text
South Asia (Mumbai)
```

Use direct PostgreSQL access from the FastAPI backend. You do not need Supabase Data API or `supabase-js` for this architecture.

Use the Session Pooler connection string, not the browser/frontend client.

The connection string will look like:

```text
postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres
```

Put the real value in Render as:

```env
DATABASE_URL_OVERRIDE=<your Supabase Session Pooler URI>
```

Do not put it in GitHub.

## Step 3: Deploy Backend on Render

Create a new Render Web Service.

Use these settings:

```text
Source: your GitHub ScanMyBill repository
Branch: main
Runtime/Language: Docker
Instance: Free
Root Directory: backend
Docker Build Context Directory: backend/
Dockerfile Path: backend/
Health Check Path: /health/live
Docker Command: blank
Pre-Deploy Command: blank
Disk: none
Auto Deploy: On Commit
```

Render path fields are relative to the repository root. For this project, keep both Docker build context and Dockerfile path pointing at `backend/`.

### Backend Docker Port

The backend Dockerfile must let Render choose the runtime port:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
```

Do not hard-code Uvicorn to only port `8000` for Render.

## Step 4: Configure Render Environment Variables

Minimum backend production values:

```env
ENVIRONMENT=production
DEBUG=false
ENABLE_DOCS=false
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
ENFORCE_HTTPS=true
TRUST_PROXY_HEADERS=true
SEED_DEFAULT_ADMIN=false
EXPOSE_PASSWORD_RESET_TOKEN=false
UPLOADS_DIR=uploads

DATABASE_URL_OVERRIDE=<your Supabase Session Pooler URI>
SECRET_KEY=<long random secret>
```

After Vercel gives you the frontend URL, add:

```env
CORS_ORIGINS=https://your-vercel-domain.vercel.app
TRUSTED_HOSTS=your-render-backend.onrender.com,your-vercel-domain.vercel.app
```

Important:

- `CORS_ORIGINS` includes `https://`.
- `TRUSTED_HOSTS` does not include `https://`.
- Do not use `localhost`, `127.0.0.1`, or `0.0.0.0` in production values.

Optional backend values:

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_IDS=
NEXT_PUBLIC_GOOGLE_CLIENT_ID=

OPENAI_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=

RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_PLAN_ID=
RAZORPAY_WEBHOOK_SECRET=

SMTP_HOST=
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_SENDER_EMAIL=
```

## Step 5: Verify Render Backend

Open:

```text
https://your-render-backend.onrender.com/health/live
```

Expected response:

```json
{"status":"ok"}
```

If Render fails with security validation like this:

```text
CORS_ORIGINS cannot include localhost or loopback values in production.
TRUSTED_HOSTS cannot include localhost or loopback values in production.
```

fix Render environment variables. Do not bypass the validation in code.

## Step 6: Deploy Frontend on Vercel

Import the GitHub repository into Vercel.

Use these settings:

```text
Framework Preset: Next.js
Root Directory: frontend
Build Command: default / npm run build
Install Command: default
Output Directory: Next.js default / blank
```

Critical warning:

Do not set the Vercel project to:

```text
Framework Preset: Other
Output Directory: public
Output Directory: .
Output Directory: .next
Output Directory: .next/standalone
Output Directory: frontend/.next
```

If Vercel is misconfigured as `Other`, the build can still show that `/` was generated, but production may return:

```text
GET / -> 404
Cache key: /404.html
Middleware: 200
```

That means Vercel is treating the deployment as static output instead of a Next.js app.

Correct settings:

```text
Framework Preset: Next.js
Output Directory: Next.js default
```

## Step 7: Configure Vercel Environment Variables

Minimum frontend values:

```env
NEXT_PUBLIC_APP_URL=https://your-vercel-domain.vercel.app
NEXT_PUBLIC_API_URL=https://your-render-backend.onrender.com/api/v1
NEXT_PUBLIC_SESSION_IDLE_TIMEOUT_MINUTES=30
NEXT_PUBLIC_IDLE_TIMEOUT_MINUTES=30
```

Optional:

```env
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<your Google OAuth client ID>
NEXT_PUBLIC_RAZORPAY_KEY_ID=<your Razorpay public key>
```

Important:

```env
NEXT_PUBLIC_APP_URL=https://your-vercel-domain.vercel.app
NEXT_PUBLIC_API_URL=https://your-render-backend.onrender.com/api/v1
```

Do not reverse these.

## Step 8: Update Render CORS After Vercel URL Exists

After Vercel deployment, return to Render and set:

```env
CORS_ORIGINS=https://your-vercel-domain.vercel.app
TRUSTED_HOSTS=your-render-backend.onrender.com,your-vercel-domain.vercel.app
```

Redeploy the Render backend.

Verify again:

```text
https://your-render-backend.onrender.com/health/live
```

## Step 9: Google OAuth Setup

In Google Cloud Console, configure the OAuth client.

Authorized JavaScript origins:

```text
http://localhost:3000
https://your-vercel-domain.vercel.app
```

Do not add paths to JavaScript origins.

Authorized redirect URIs:

```text
http://localhost:3000/api/auth/callback/google
https://your-render-backend.onrender.com/api/v1/auth/google/callback
```

Set the same Google client ID in:

```env
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<client ID>
GOOGLE_CLIENT_ID=<client ID>
```

If Google login fails with `origin_mismatch`, check the JavaScript origins first.

## Step 10: Admin Account Notes

Admin identity is environment-driven:

```env
DEFAULT_ADMIN_USER_ID=admin
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_FULL_NAME=Admin User
```

The admin password is secret and must not be printed or committed.

In production:

```env
SEED_DEFAULT_ADMIN=false
```

Do not turn on admin seeding casually in production. If the admin password is unknown, reset it with a controlled backend/admin reset flow or a database-side bcrypt reset. Do not try to recover the old password.

## Step 11: Common Problems and Fixes

### Render Builds but App Fails at Startup

Symptom:

```text
Security configuration error(s):
CORS_ORIGINS cannot include localhost or loopback values in production.
TRUSTED_HOSTS cannot include localhost or loopback values in production.
```

Fix:

```env
CORS_ORIGINS=https://your-vercel-domain.vercel.app
TRUSTED_HOSTS=your-render-backend.onrender.com,your-vercel-domain.vercel.app
```

### Render Port Issue

Symptom:

Render deployment never becomes healthy even though Docker builds.

Fix:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
```

### Vercel Middleware Rejects Alias Import

Symptom:

```text
The Edge Function "middleware" is referencing unsupported modules:
@/lib/subscription-access
```

Fix:

Use a relative import in `frontend/middleware.ts`:

```ts
import {
  canAccessAppPath,
  isAppProtectedPath,
  resolveEffectiveSubscriptionPlan,
} from './lib/subscription-access';
```

### Vercel Middleware Crashes with `__dirname`

Symptom:

```text
ReferenceError: __dirname is not defined
MIDDLEWARE_INVOCATION_FAILED
```

Cause:

The middleware imported from the public `next/server` barrel, which pulled in framework code not safe for this Edge bundle.

Fix:

```ts
import type { NextRequest } from 'next/dist/server/web/spec-extension/request';
import { NextResponse } from 'next/dist/server/web/spec-extension/response';
```

### Vercel Returns `/404.html` Even Though Build Shows `/`

Symptom:

```text
GET / -> 404
Middleware: 200
Cache key: /404.html
```

Cause:

Vercel project is configured as static/Other instead of Next.js.

Fix:

```text
Framework Preset: Next.js
Root Directory: frontend
Output Directory: Next.js default / blank
```

Trigger a new production deployment after changing settings.

## Step 12: Verification Checklist

Frontend:

```text
https://your-vercel-domain.vercel.app/
```

Expected:

```text
200 OK
X-Matched-Path: /
```

Backend:

```text
https://your-render-backend.onrender.com/health/live
```

Expected:

```json
{"status":"ok"}
```

Local frontend build:

```bash
cd frontend
npm run build
```

Expected:

```text
Compiled successfully
○ /
ƒ Middleware
```

Generated route check:

```text
frontend/.next/routes-manifest.json includes page "/"
frontend/.next/server/app/index.html exists
```

## Step 13: End-to-End Test Sequence

Run these tests after deployment:

1. Open the Vercel frontend.
2. Test Google Sign-In.
3. Test email/password signup.
4. Test email/password login.
5. Refresh after login.
6. Logout.
7. Login again.
8. Test dashboard data retrieval.
9. Test invoice upload.
10. Test OCR.
11. Test AI extraction.
12. Verify invoice database persistence.
13. Test sales/purchase analytics.
14. Test admin login.
15. Test password reset.
16. Test Razorpay only after auth/database flows work.
17. Test SMTP only after email configuration is ready.

## Free Tier Caveats

Render Free can sleep after inactivity. The first backend request after sleep may be slow.

Render Free local filesystem is not durable. Uploaded invoice files can disappear after restart or redeploy.

Supabase Free has limits and may pause inactive projects depending on current Supabase policy.

Vercel Hobby has usage limits and is intended for personal/non-enterprise use.

AI, OCR enhancements, email, payments, and storage can create costs depending on provider usage.

Always check current provider limits before relying on this setup for real customers.

## Production Hardening Later

Before treating this as serious production:

- Rotate any exposed Supabase database password.
- Move uploaded invoice files to Supabase Storage or S3-compatible storage.
- Add Alembic migrations.
- Add monitoring/logging alerts.
- Review rate limits.
- Review Razorpay webhook verification.
- Review OAuth consent screen and authorized domains.
- Use paid hosting if uptime matters.
- Keep secrets only in provider secret stores.

## Quick Reference

Production frontend:

```text
https://your-vercel-domain.vercel.app
```

Production backend:

```text
https://your-render-backend.onrender.com
```

Backend API:

```text
https://your-render-backend.onrender.com/api/v1
```

Backend health:

```text
https://your-render-backend.onrender.com/health/live
```

Frontend env:

```env
NEXT_PUBLIC_APP_URL=https://your-vercel-domain.vercel.app
NEXT_PUBLIC_API_URL=https://your-render-backend.onrender.com/api/v1
```

Backend CORS/trusted hosts:

```env
CORS_ORIGINS=https://your-vercel-domain.vercel.app
TRUSTED_HOSTS=your-render-backend.onrender.com,your-vercel-domain.vercel.app
```

