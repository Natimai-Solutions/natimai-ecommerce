import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'
import { LOCALE, STOREFRONT_URL } from '../../support/env'
import { gotoHydrated } from '../../support/storefront'

/**
 * A dated promotion on one article: the storefront shows the promotional
 * price, the usual price struck through and the discount. Best-price rule
 * (no stacking with group prices) is covered by the backend tests. The
 * promotion is switched off at the end.
 */
test('a promotion shows the struck-through price on the storefront', async ({
  page,
  browser,
}) => {
  const name = `Promo e2e ${Date.now().toString(36)}`
  const today = new Date()
  const nextWeek = new Date(today.getTime() + 7 * 24 * 3600 * 1000)
  const iso = (d: Date) => d.toISOString().slice(0, 10)

  await loginAdmin(page, '/promotions')
  await page.getByTestId('promotion-create').click()
  const dialog = page.getByTestId('promotion-dialog')
  await dialog.getByTestId('promotion-name').fill(name)
  await dialog.getByTestId('promotion-product').fill('Station de travail')
  await page.getByRole('option', { name: /Station de travail E2E/ }).click()
  await dialog.getByTestId('promotion-percentage').fill('20')
  await dialog.getByLabel('Du').fill(iso(today))
  await dialog.getByLabel('Au (inclus)').fill(iso(nextWeek))
  await dialog.getByTestId('promotion-save').click()
  await expect(dialog).toBeHidden()
  const row = page.locator('tr', { hasText: name })
  await expect(row).toContainText('En cours')
  await expect(row).toContainText('Station de travail E2E')

  const shopContext = await browser.newContext({ baseURL: STOREFRONT_URL, locale: LOCALE })
  const shop = await shopContext.newPage()
  try {
    await gotoHydrated(shop, '/catalogue')
    const card = shop.getByTestId('product-card').filter({ hasText: 'Station de travail E2E' })
    await expect(card.getByTestId('product-card-promo')).toContainText('−20 %')
    await card.getByRole('link', { name: 'Station de travail E2E' }).click()
    await expect(shop.getByTestId('product-promo')).toContainText(name)
    await expect(shop.getByTestId('product-promo').locator('s')).toBeVisible()
  } finally {
    await shopContext.close()
    await row.locator('.q-toggle').click()
    await expect(row).toContainText('Désactivée')
  }
})
