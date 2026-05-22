# Test Coverage Gaps (backend/app)

Date: 2026-05-15
Source: execution under coverage.py on current branch.
Command:
- c:/Dev/fastapi-ecommerce/backend/.venv/Scripts/python.exe -m coverage run -m pytest backend/app/tests
- c:/Dev/fastapi-ecommerce/backend/.venv/Scripts/python.exe -m coverage json -o backend/coverage.json
- c:/Dev/fastapi-ecommerce/backend/.venv/Scripts/python.exe -m coverage report -m

## Snapshot

- Tests: 236 passed, 1 failed
- Failing test: backend/app/tests/test_phase_e4_preprod_rollback_doc.py
- Failure reason: missing file backend/CHECKLIST_PREPROD_ROLLBACK_E4.md
- Total coverage (backend/app): 77.01%
- Files at 0% coverage: none

## Interpretation

This document lists features considered not covered enough by tests.
Rule used:
- High gap: module coverage < 40%
- Medium gap: module coverage >= 40% and < 60%

Note: a module with low percentage can still have some tests. The goal here is to identify insufficiently validated features.

## High Gap Features (< 40%)

### 1) Supplier and external catalog flows
- Legacy Payzen utility internals: backend/app/features/payment/utils/payzen.py (13.79%)
- Icecat service orchestration: backend/app/services/icecat_service.py (14.39%)
- Icecat background jobs: backend/app/tasks/icecat_tasks.py (16.67%)
- Supplier sync CRUD: backend/app/features/integrations/crud/supplier_sync.py (24.24%)
- Ingram Micro adapter: backend/app/services/suppliers/ingram_micro.py (25.12%)
- Supplier tasks orchestration: backend/app/tasks/supplier_tasks.py (33.57%)

Coverage signal: provider/API edge cases and failure paths are mostly untested.

### 2) Shipping routing engine internals
- Route graph and path search CRUD: backend/app/features/shipping/crud/route.py (16.50%)
- Delivery task CRUD logic: backend/app/features/shipping/crud/delivery_task.py (23.19%)
- Route tracking CRUD lifecycle: backend/app/features/shipping/crud/route_tracking.py (31.15%)

Coverage signal: core routing algorithms and tracking transitions need deeper unit testing.

### 3) Place and partner business CRUD
- Place CRUD: backend/app/features/place/crud.py (19.23%)
- Partner CRUD: backend/app/features/partner/crud.py (35.71%)

Coverage signal: country filters, nearest place logic, and partner route lookups are not sufficiently exercised.

### 4) User side CRUD (notification, wishlist, review, refresh token, address)
- User notification CRUD: backend/app/features/user/crud/notification.py (22.86%)
- Wishlist CRUD: backend/app/features/user/crud/wishlist.py (26.58%)
- Review CRUD: backend/app/features/user/crud/review.py (31.82%)
- Refresh token CRUD: backend/app/features/user/crud/refresh_token.py (31.82%)
- Address CRUD: backend/app/features/user/crud/address.py (37.93%)

Coverage signal: data workflows are exposed by API but CRUD edge/error branches remain under-tested.

### 5) Cart and discount internals
- Cart CRUD internals: backend/app/features/cart/crud/cart.py (27.16%)
- Discount CRUD internals: backend/app/features/discount/crud.py (25.53%)

Coverage signal: business helper paths are only partially reached through API tests.

### 6) Outbox runtime infrastructure
- Poller runtime and retry loop: backend/app/outbox/poller.py (30.57%)
- Handler discovery loader: backend/app/outbox/loader.py (38.60%)

Coverage signal: continuous polling/retry/error handling and dynamic loading paths are not deeply tested.

## Medium Gap Features (40% to 60%)

### API surfaces with limited scenario coverage
- Suppliers routes: backend/app/api/routes/suppliers.py (58.24%)
- Icecat routes: backend/app/api/routes/icecat.py (45.45%)
- Address routes: backend/app/api/routes/address.py (46.58%)
- Group routes: backend/app/api/routes/group.py (48.08%)
- User notification routes: backend/app/api/routes/user_notification.py (55.41%)
- User review routes: backend/app/api/routes/user_review.py (45.88%)
- User wishlist routes: backend/app/api/routes/user_wishlist.py (46.48%)

### Runtime/infra modules
- Outbox decorators: backend/app/outbox/decorators.py (45.83%)
- Attachment storage factory branching: backend/app/features/attachment/storage/factory.py (44.00%)

### Business orchestration modules
- Supplier sync orchestrator: backend/app/features/integrations/services/supplier_sync_orchestrator.py (53.42%)

## Suggested Test Backlog

### Priority A (critical business/runtime)
- Add unit tests for backend/app/features/shipping/crud/route.py:
  - path exploration depth limits
  - prefer_direct behavior
  - no-path and multi-path ordering cases
- Add unit tests for backend/app/outbox/poller.py:
  - retry backoff sequence
  - transition RUNNING -> PENDING on enqueue failure
  - handling of missing handler registration
- Add unit tests for backend/app/services/suppliers/ingram_micro.py and backend/app/services/icecat_service.py:
  - HTTP error handling
  - pagination/retry behavior
  - normalization mapping edge cases

### Priority B (user and commerce CRUD)
- Add CRUD-level tests for wishlist/review/notification/refresh_token/address modules.
- Add CRUD-level tests for cart and discount modules on branches not reached by API flows.

### Priority C (API scenario depth)
- Extend route tests for suppliers/icecat/address/group/user_* with:
  - auth forbidden paths
  - invalid payload/body/query combinations
  - empty and boundary results

## Notes for next run

- Fix or restore backend/CHECKLIST_PREPROD_ROLLBACK_E4.md so test suite is fully green before using this report as CI baseline.
- Re-run coverage after adding Priority A tests first, then update this document.
