# Working on this repository

Monorepo: `backend/` (FastAPI, Python, `uv`), `frontend/` (storefront, Quasar),
`admin-frontend/` (back office, Quasar), `shared/` (`@app/api-types`,
`@app/utils`, `@app/ui`). Day-to-day details: `docs/DEVELOPMENT.md`;
operations: `docs/DEPLOYMENT.md`; what is left to do: `docs/internal/PLAN_DE_TRAVAIL.md`.

## Languages (decision of 18/11/2026)

- **The API is language-agnostic.** An error is `{ code, message, details }`:
  the interfaces translate the `code` from the shared catalogue
  `shared/utils/src/apiErrors/{en,fr}.json`; `message` is only the English
  fallback.
- **Backend messages are in English**, word for word the catalogue's English
  text, `{placeholders}` included (`AppError` fills them from `details`; put
  the values in `details`). Never write an API message in French.
- **A new error code goes into both catalogue files in the same change**;
  `backend/app/tests/test_api_error_catalog.py` enforces it.
- **Frontends never display a server text**: errors through
  `apiErrorMessage` (storefront) / `extractApiError` (admin); success texts
  from their own i18n files (`src/i18n/{fr,en}.ts`), in both languages.
- E-mails, PDFs and catalogue content are rendered and translated server-side
  (`app/templates/*/{fr,en}`, `translations` columns): they stay there.
- **Messages to the operator** (alerts to `ALERT_WEBHOOK_URL`, staff
  notifications, the support's quote e-mail) are rendered server-side in the
  operator's language (setting `operator_locale`, default the shop's): add a
  key to `app/core/operator_messages.py` in English and French, send it with
  `alert(key, source=…, **values)` / `operator_text(key, **values)`. Never a
  French or English literal in `send_alert`.

## Habits of this repository

- Talk to the owner in French. Code, comments, CHANGELOG, tests: English;
  commit messages, the work plan and the audits: French.
- Every change updates `CHANGELOG.md` (Unreleased) and, when it closes or opens
  an item, `docs/internal/PLAN_DE_TRAVAIL.md` (it lists only what is left).
- A schema change comes with its Alembic migration (check it upgrades and
  downgrades) and `pnpm gen:types` (commit `shared/api-types/src/schema.ts`).
- Tests on a real database for anything touching orders, payments or stock
  (`backend/app/tests/integration/`, `TEST_DATABASE_URL`); unit tests with
  mocks miss what broke in November 2026.
- Before pushing: `uv run ruff check`, `uv run ruff format --check`,
  `uv run mypy app` (backend); `pnpm typecheck`, `pnpm lint` (each app),
  `npx vitest run` (root).
