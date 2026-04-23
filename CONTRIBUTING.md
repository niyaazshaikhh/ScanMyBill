# Contributing

Last updated: April 23, 2026

## Local Setup

1. Copy `.env.example` to `.env`.
2. Copy `backend/.env.example` to `backend/.env`.
3. Copy `frontend/.env.example` to `frontend/.env`.
4. Fill in only the values you need for local development.

## Safety Rules

- Never commit `.env`, `backend/.env`, or `frontend/.env`.
- Use placeholder values in examples and docs.
- Put real secrets in local env files, GitHub Secrets, or your cloud secret manager.
- If you need a new config variable, add it to the relevant `*.env.example` file and document it.

## Before Opening a PR

- Run backend tests.
- Run frontend lint and build checks.
- Check that no secrets or machine-specific values were added to tracked files.
- Update docs when behavior, setup, or deployment steps change.
