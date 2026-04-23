# Security Policy

Last updated: April 23, 2026

## Supported Branch

- `main`: supported for security fixes

## Reporting a Vulnerability

Please do not open a public issue for undisclosed vulnerabilities.

Preferred process:

1. Use GitHub private vulnerability reporting or a private security advisory if it is enabled for this repository.
2. If private reporting is not enabled, contact the repository maintainer through a private channel listed in the repository settings or profile.
3. Include reproduction steps, impact, affected files or endpoints, and any suggested mitigation.

## Maintainer Expectations

- Acknowledge reports promptly.
- Reproduce and triage the issue before public discussion.
- Ship a fix and rotate affected credentials if secrets may have been exposed.
- Publish a follow-up advisory or changelog entry after a fix is available.

## Repository Hygiene

- Never commit populated env files or cloud credentials.
- Keep production secrets in GitHub Secrets, Azure secrets, or another managed secret store.
- If a secret was ever committed, rotate it and rewrite history before making the repository public.
