# GitHub Publishing Checklist

Last updated: April 23, 2026

Use this checklist before pushing the repository to a public GitHub remote.

## 1. Remove Local Secrets From Tracking

- Keep `.env`, `backend/.env`, and `frontend/.env` local-only.
- Confirm only `*.env.example` files are tracked.
- Check deployment helper files for org, repo, tenant, subscription, or secret values.

## 2. Rotate Anything Sensitive

If a real secret was ever committed locally or pushed anywhere:

- Rotate database passwords
- Rotate `SECRET_KEY`
- Rotate OpenAI or Azure OpenAI keys
- Rotate SMTP credentials
- Rotate Razorpay secrets
- Rotate any OAuth credentials

If secrets were already pushed, rewrite history before publishing.

## 3. Review Production Configuration

- Set exact `CORS_ORIGINS` values
- Set exact `TRUSTED_HOSTS` values
- Set `COOKIE_SECURE=true`
- Set `ENFORCE_HTTPS=true`
- Set `ENABLE_DOCS=false`
- Keep `SEED_DEFAULT_ADMIN=false`
- Keep `EXPOSE_PASSWORD_RESET_TOKEN=false`

## 4. Prepare GitHub and Azure

- Replace placeholders in `github-env.json`
- Replace placeholders in `github-oidc.json`
- Add required GitHub Secrets
- Add required GitHub Variables
- Verify production URLs are HTTPS and not `localhost`

## 5. Enable Ongoing Maintenance

- Enable Dependabot alerts and security updates in GitHub
- Enable private vulnerability reporting if this repo will be public
- Review workflow permissions and environment protection rules

## 6. Final Sanity Check

Run these before publishing:

```bash
git status
git ls-files
python -m unittest discover -s backend/tests -p "test_*.py"
cd frontend && npm run lint
```
