import { expect, test, type Page } from '@playwright/test'

/**
 * The signed-in customer area (« Mon compte »): navigation between sections,
 * the order list and an order's detail page, and a profile edit.
 *
 * Runs after checkout.spec.ts (files run in name order, one worker), so the
 * customer normally has at least the order that journey placed; the order
 * steps still hold if this file runs alone against a fresh seed.
 */

const CUSTOMER_EMAIL = process.env.E2E_EMAIL ?? 'e2e-customer@example.com'
const CUSTOMER_PASSWORD = process.env.E2E_PASSWORD ?? 'e2e-customer-password-123'

async function gotoHydrated(page: Page, path: string) {
  await page.goto(path)
  await page.locator('html[data-hydrated]').waitFor({ state: 'attached' })
}

async function login(page: Page) {
  await gotoHydrated(page, '/connexion')
  await page.getByTestId('login-email').fill(CUSTOMER_EMAIL)
  await page.getByTestId('login-password').fill(CUSTOMER_PASSWORD)
  await page.getByTestId('login-submit').click()
  await expect(page).not.toHaveURL(/connexion/)
}

test('a customer finds their orders and edits their profile', async ({ page }) => {
  await login(page)

  await test.step('the account opens on the overview, with its sections', async () => {
    await page.getByRole('link', { name: 'Mon compte' }).first().click()
    await expect(page).toHaveURL(/mon-compte/)
    await expect(page.getByTestId('account-nav-overview')).toHaveAttribute('aria-current', 'page')
  })

  await test.step('orders list and an order detail', async () => {
    await page.getByTestId('account-nav-orders').click()
    await expect(page).toHaveURL(/tab=orders/)
    const list = page.getByTestId('account-orders')
    const empty = page.getByText("Aucune commande pour l'instant")
    await expect(list.or(empty)).toBeVisible()
    if (await list.isVisible()) {
      await list.getByRole('link', { name: 'Détail' }).first().click()
      // The detail is titled with the sequential reference, never the UUID.
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(/CMD-\d{4}-\d{5,}/)
      await expect(page.getByTestId('order-lines')).toBeVisible()
      await page.getByRole('link', { name: 'Mes commandes' }).click()
      await expect(page).toHaveURL(/tab=orders/)
    }
  })

  await test.step('profile edit is saved', async () => {
    await page.getByTestId('account-nav-profile').click()
    const form = page.getByTestId('account-profile')
    await expect(form).toBeVisible()
    const name = `Client E2E ${Date.now() % 10000}`
    await form.getByLabel('Nom complet').fill(name)
    await form.getByRole('button', { name: 'Enregistrer' }).click()
    await expect(form.getByText('Profil enregistré.')).toBeVisible()
    await page.reload()
    await page.locator('html[data-hydrated]').waitFor({ state: 'attached' })
    await expect(page.getByTestId('account-profile').getByLabel('Nom complet')).toHaveValue(name)
  })
})
