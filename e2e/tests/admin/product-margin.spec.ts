import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'

/**
 * Margin of a manually priced article: the product form shows it live from
 * the price and the purchase cost, and the product list sorts by it. The
 * default VAT rate (16 %) applies: 11 600 TTC = 10 000 HT, cost 6 000 →
 * margin 4 000, 40 % of the price excl. tax.
 */
test('the admin sees and sorts the margin of a fixed-price article', async ({ page }) => {
  const name = `Casque marge ${Date.now().toString(36)}`

  await loginAdmin(page, '/products')
  await page.getByRole('button', { name: 'Nouveau produit' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Nom *').fill(name)
  await dialog.getByText('Prix TTC fixé').click()
  await dialog.getByTestId('product-base-price').fill('11600')
  await dialog.getByTestId('product-cost').fill('6000')

  const panel = dialog.getByTestId('margin-panel')
  await expect(panel.getByTestId('margin-amount')).toHaveText(/4\s?000/)
  await expect(panel.getByTestId('margin-pct')).toContainText('40 %')

  // Sold below cost: the panel says so.
  await dialog.getByTestId('product-base-price').fill('5800')
  await expect(panel).toContainText('Vendu à perte')
  await dialog.getByTestId('product-base-price').fill('11600')
  await expect(panel.getByTestId('margin-amount')).toHaveText(/4\s?000/)

  await dialog.getByRole('button', { name: 'Créer' }).click()
  await expect(dialog).toBeHidden()

  await page.getByTestId('products-sort').click()
  await page.getByRole('option', { name: 'Marge HT décroissante' }).click()
  const row = page.locator('tr', { hasText: name })
  await expect(row.getByTestId('product-margin')).toContainText(/4\s?000/)
  await expect(row.getByTestId('product-margin')).toContainText('40 %')
})
