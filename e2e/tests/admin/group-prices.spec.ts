import { expect, test } from '@playwright/test'

import { loginAdmin, openAdmin } from '../../support/admin'

/**
 * Prices per customer group: a discount for the professionals on every
 * article, and a price typed for the public establishments on one article.
 * The product form shows what each group pays and the margin left; the typed
 * price survives a reopening. The discount is reset at the end.
 */
test('the admin sets a group discount and a group price on an article', async ({ page }) => {
  const name = `Casque groupes ${Date.now().toString(36)}`

  await loginAdmin(page, '/price-groups')
  const pro = page.getByTestId('price-group-PROFESSIONNEL')
  await pro.getByTestId('price-group-discount-PROFESSIONNEL').fill('10')
  await pro.getByTestId('price-group-save-PROFESSIONNEL').click()
  await expect(page.getByText('Remise « Professionnel » enregistrée : 10 %.')).toBeVisible()

  try {
    await openAdmin(page, '/products')
    await page.getByRole('button', { name: 'Nouveau produit' }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel('Nom *').fill(name)
    await dialog.getByText('Prix TTC fixé').click()
    await dialog.getByTestId('product-base-price').fill('11600')
    await dialog.getByTestId('product-cost').fill('6000')

    const grid = dialog.getByTestId('group-prices')
    await expect(grid.getByTestId('group-price-paid-Particulier')).toHaveText(/11\s?600/)
    await expect(grid.getByTestId('group-price-paid-Professionnel')).toHaveText(/10\s?440/)
    await grid.getByTestId('group-price-input-Public / Etablissements').fill('9900')
    await expect(grid.getByTestId('group-price-paid-Public / Etablissements')).toHaveText(
      /9\s?900/,
    )

    await dialog.getByRole('button', { name: 'Créer' }).click()
    await expect(dialog).toBeHidden()

    // Reopened: the typed price is still there.
    await page.getByLabel('Rechercher (nom, SKU, MPN)').fill(name)
    // Wait for the filtered list (the search is debounced) before clicking.
    await expect(page.locator('tbody tr')).toHaveCount(1)
    const row = page.locator('tr', { hasText: name })
    await row.getByRole('button', { name: 'Modifier' }).click()
    await expect(dialog.getByTestId('group-prices')).toBeVisible()
    // Quasar puts the test id on the native input.
    await expect(dialog.getByTestId('group-price-input-Public / Etablissements')).toHaveValue(
      '9900',
    )
    await dialog.getByRole('button', { name: 'Annuler' }).click()
  } finally {
    await openAdmin(page, '/price-groups')
    await page.getByTestId('price-group-discount-PROFESSIONNEL').fill('0')
    await page.getByTestId('price-group-save-PROFESSIONNEL').click()
    await expect(page.getByText('Remise « Professionnel » enregistrée : 0 %.')).toBeVisible()
  }
})
