# Security policy

This platform handles payments (PayZen / Lyra, manual methods), customer
accounts (passwords, one-time codes, OAuth), uploaded documents (purchase
orders, scanned by ClamAV) and legally numbered invoices. Treat anything in
those areas as sensitive.

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private reporting:

**Security → Advisories → [Report a vulnerability](https://github.com/Natimai-Solutions/natimai-ecommerce/security/advisories/new)**

Include what you found, how to reproduce it, the commit or tag you tested, and
the impact you expect. You will get an acknowledgement within a few days and a
status update once the report has been triaged. Fixes land on `main` first;
the advisory is published, with credit if you want it, once a fix is released.

If private reporting is not available on the repository, contact the
maintainer ([@jburckel](https://github.com/jburckel)) through GitHub.

## Supported versions

Only the latest release and `main` receive fixes. Deployments are expected to
follow tagged releases (see `CHANGELOG.md`).

## What is already in place

- `.github/workflows/security.yml` runs on every pull request and weekly:
  gitleaks (committed secrets), pip-audit and `pnpm audit` on the production
  lockfiles, Trivy on the three Docker images, CodeQL when enabled.
- The backend refuses to start outside `ENVIRONMENT=local` with placeholder
  secrets (`changethis` or any `changeme-…` value of `.env.example`), a
  disabled antivirus, or a short `SECRET_KEY`.
- Dependabot keeps Python, JavaScript, Docker base images and GitHub Actions
  up to date (`.github/dependabot.yml`).

## Out of scope

Issues that require a compromised server or database, self-inflicted
misconfiguration explicitly warned about in `docs/DEPLOYMENT.md`, and
vulnerabilities in third-party services (PayZen, Mailgun, Ingram Micro,
Icecat) themselves.
