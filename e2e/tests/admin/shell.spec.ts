import { expect, test } from '@playwright/test'

import { adminPath, loginAdmin, openAdmin, watchForBreakage } from '../../support/admin'
import { ADMIN_EMAIL } from '../../support/env'

/**
 * The admin shell: access control, the dashboard, and every screen of the
 * menu opening without an exception or a server error — the smoke test that
 * catches a broken page before an admin does.
 */

test('an anonymous visitor is sent to the login, then back where they were going', async ({
  page,
}) => {
  await page.goto(adminPath('/orders'))
  await expect(page).toHaveURL(/#\/login\?redirect=/)

  await page.getByTestId('admin-login-email').fill(ADMIN_EMAIL)
  await page.getByTestId('admin-login-password').fill('not-the-password')
  await page.getByTestId('admin-login-submit').click()
  await expect(page.getByTestId('admin-login-error')).toBeVisible()
  await expect(page).toHaveURL(/#\/login/)

  await loginAdmin(page, '/orders')
  await expect(page).toHaveURL(/#\/orders$/)
})

test('the dashboard lists the work queues', async ({ page }) => {
  const problems = watchForBreakage(page)
  await loginAdmin(page)
  await expect(page.getByTestId('nav-dashboard')).toHaveClass(/admin-nav__link--active/)
  const queues = page.getByTestId('dashboard-todo')
  await expect(queues.getByTestId('todo-orders_to_process')).toBeVisible()
  await expect(queues.getByTestId('todo-payments_to_validate')).toBeVisible()
  await expect(queues.getByTestId('todo-quote_requests_open')).toBeVisible()
  await expect(queues.getByTestId('todo-group_upgrade_requests_pending')).toBeVisible()
  expect(problems).toEqual([])
})

test('every menu entry opens its screen without error', async ({ page }) => {
  const problems = watchForBreakage(page)
  await loginAdmin(page)

  const entries = await page.locator('[data-testid^="nav-"]').evaluateAll((links) =>
    links.map((link) => ({
      id: link.getAttribute('data-testid') ?? '',
      hash: new URL((link as HTMLAnchorElement).href).hash,
    })),
  )
  // Guard: the scan must really find the menu (six sections, ~30 screens).
  expect(entries.length).toBeGreaterThan(20)

  for (const entry of entries) {
    await test.step(entry.id, async () => {
      await page.getByTestId(entry.id).click()
      await expect(page).toHaveURL(new RegExp(`${entry.hash.replace(/[/?]/g, '\\$&')}$`))
      await expect(page.getByTestId(entry.id)).toHaveClass(/admin-nav__link--active/)
      await expect(page.getByTestId('page-title')).toBeVisible()
      await page.waitForLoadState('networkidle')
      expect(problems, `${entry.id} (${entry.hash})`).toEqual([])
    })
  }
})

test('the theme choice survives a reload', async ({ page }) => {
  await loginAdmin(page)

  await page.getByTestId('admin-theme').click()
  await page.getByTestId('theme-dark').click()
  await expect(page.locator('body')).toHaveClass(/body--dark/)

  // A full reload also proves the session comes back from the refresh cookie.
  await page.reload()
  await expect(page.getByTestId('page-title')).toBeVisible()
  await expect(page.locator('body')).toHaveClass(/body--dark/)

  await page.getByTestId('admin-theme').click()
  await page.getByTestId('theme-light').click()
  await expect(page.locator('body')).not.toHaveClass(/body--dark/)
})

test('logging out closes the session', async ({ page }) => {
  await loginAdmin(page)
  await page.getByTestId('admin-account').click()
  await page.getByTestId('admin-logout').click()
  await expect(page).toHaveURL(/#\/login/)

  await openAdmin(page, '/orders')
  await expect(page).toHaveURL(/#\/login\?redirect=/)
})
