import { expect, type Page } from '@playwright/test'

import { ADMIN_EMAIL, ADMIN_PASSWORD } from './env'

/**
 * The admin is a hash-routed SPA: every screen lives under `/#/…`. The page
 * must use the admin as baseURL.
 */
export function adminPath(path: string): string {
  return `/#${path.startsWith('/') ? path : `/${path}`}`
}

/**
 * Sign in through the login form, then land on `path` (the dashboard by
 * default). The access token lives in memory only, so navigate inside the app
 * afterwards (hash changes), never with a full reload unless the test is
 * about the refresh-cookie restore.
 */
export async function loginAdmin(page: Page, path = '/') {
  await page.goto(adminPath(`/login?redirect=${encodeURIComponent(path)}`))
  await page.getByTestId('admin-login-email').fill(ADMIN_EMAIL)
  await page.getByTestId('admin-login-password').fill(ADMIN_PASSWORD)
  await page.getByTestId('admin-login-submit').click()
  await expect(page).not.toHaveURL(/#\/login/)
  await expect(page.getByTestId('page-title')).toBeVisible()
}

/** Navigate inside the SPA without reloading (keeps the in-memory session). */
export async function openAdmin(page: Page, path: string) {
  await page.evaluate((hash) => {
    window.location.hash = hash
  }, path)
}

/**
 * Collect what must never happen on an admin screen: an uncaught exception,
 * or an API call answered by a server error.
 */
export function watchForBreakage(page: Page): string[] {
  const problems: string[] = []
  page.on('pageerror', (error) => problems.push(`exception: ${error.message}`))
  page.on('response', (response) => {
    if (response.status() >= 500) problems.push(`${response.status()} ${response.url()}`)
  })
  return problems
}
