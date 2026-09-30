import { defineConfig, devices } from '@playwright/test'

import { ADMIN_URL, STOREFRONT_URL } from './support/env'

/**
 * End-to-end configuration (Q4).
 *
 * The suite runs against an already-running stack rather than starting one
 * itself: the storefront is a Quasar SSR app served from a container, and
 * `docker compose up` is the same command CI and a developer would use. See
 * e2e/README.md for the two commands that bring it up.
 */

export default defineConfig({
  testDir: './tests',
  // One worker: the journey consumes seeded stock and mutates the customer's
  // cart, so parallel runs would fight over the same fixtures.
  workers: 1,
  fullyParallel: false,
  // Fail the run rather than silently pass if someone leaves a .only behind.
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: STOREFRONT_URL,
    // SSR hydration means the first interaction can lag; keep traces and
    // screenshots of failures so a CI red is diagnosable without a rerun.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
  },
  // Two apps, two base URLs. The admin journeys that need a storefront step
  // (a customer order, the homepage) open a second page on STOREFRONT_URL.
  projects: [
    {
      name: 'storefront',
      testIgnore: /admin\//,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'admin',
      testMatch: /admin\/.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], baseURL: ADMIN_URL },
    },
  ],
})
