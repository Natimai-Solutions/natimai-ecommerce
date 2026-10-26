import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'

/**
 * « Dupliquer » on a product row opens the creation form pre-filled from that
 * article (name suffixed, same price and cost) and creates a second, distinct
 * product; the original is left as it was.
 */
test('the admin duplicates an article into a pre-filled new product', async ({ page }) => {
  const name = `Clavier source ${Date.now().toString(36)}`
  const copyName = `${name} (copie)`

  await loginAdmin(page, '/products')
  await page.getByRole('button', { name: 'Nouveau produit' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Nom *').fill(name)
  await dialog.getByText('Prix TTC fixé').click()
  await dialog.getByTestId('product-base-price').fill('11600')
  await dialog.getByTestId('product-cost').fill('6000')
  await dialog.getByRole('button', { name: 'Créer' }).click()
  await expect(dialog).toBeHidden()

  const sourceRow = page.locator('tr', { hasText: name }).filter({ hasNotText: '(copie)' })
  await expect(sourceRow).toBeVisible()
  await sourceRow.getByTestId('product-duplicate').click()

  await expect(dialog.getByRole('heading', { name: 'Dupliquer le produit' })).toBeVisible()
  await expect(dialog.getByTestId('product-duplicate-notice')).toContainText(name)
  await expect(dialog.getByLabel('Nom *')).toHaveValue(copyName)
  // Amounts come back from the API as decimals ("11600.00"), as on any edit.
  await expect(dialog.getByTestId('product-base-price')).toHaveValue(/^11600(\.0+)?$/)
  await expect(dialog.getByTestId('product-cost')).toHaveValue(/^6000(\.0+)?$/)
  await dialog.getByRole('button', { name: 'Créer' }).click()
  await expect(dialog).toBeHidden()

  // Two distinct rows: the copy, and the untouched original.
  await expect(page.locator('tr', { hasText: copyName })).toHaveCount(1)
  await expect(sourceRow).toHaveCount(1)
})
