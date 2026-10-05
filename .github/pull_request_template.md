## What and why

<!-- One paragraph: the problem, the change, and anything a reviewer should look at first. -->

## Area

- [ ] API (`backend/`)
- [ ] Storefront (`frontend/`)
- [ ] Admin (`admin-frontend/`)
- [ ] Shared packages (`shared/`)
- [ ] Infra / CI / docs

## Checklist

- [ ] The API schema changed → `pnpm gen:types` was run and `shared/api-types/src/schema.ts` is committed
- [ ] A migration was added → `alembic heads` shows a single head
- [ ] User-facing text → both `i18n/fr.ts` and `i18n/en.ts` were updated
- [ ] Tests cover the change (or explain why not)
- [ ] Docs updated where behaviour or configuration changed (`README.md`, `docs/`, `.env.example`)
