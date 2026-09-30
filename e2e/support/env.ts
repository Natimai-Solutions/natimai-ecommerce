/**
 * Where the stack under test lives, and the accounts the suite signs in with.
 * Defaults match the CI stack (docker compose, see e2e/README.md).
 */
export const STOREFRONT_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000'
export const ADMIN_URL = process.env.E2E_ADMIN_URL ?? 'http://localhost:3001'

export const CUSTOMER_EMAIL = process.env.E2E_EMAIL ?? 'e2e-customer@example.com'
export const CUSTOMER_PASSWORD = process.env.E2E_PASSWORD ?? 'e2e-customer-password-123'

// The superuser app.initial_data creates from FIRST_SUPERUSER(_PASSWORD).
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? 'ci-superuser@example.com'
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'ci-only-password'
