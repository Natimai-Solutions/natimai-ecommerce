import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'
import { STOREFRONT_URL } from '../../support/env'
import { placeManualOrder } from '../../support/storefront'

/**
 * Payment methods built from the admin: a second transfer to another bank,
 * with its own IBAN, reaches the customer at checkout; once used it can no
 * longer be deleted, only switched off. An unused method is deleted.
 */
test('an admin adds a second bank transfer with its own IBAN', async ({ page, browser }) => {
  const suffix = Date.now().toString(36)
  const name = `Virement Banque de Tahiti ${suffix}`
  const iban = `IBAN FR76 9999 8888 7777 ${suffix.toUpperCase()}`

  await loginAdmin(page, '/payment-eligibility')
  await page.getByTestId('method-create').click()
  const dialog = page.getByTestId('method-dialog')
  await dialog.getByTestId('method-type').click()
  await page.getByRole('option', { name: 'Virement bancaire' }).click()
  await dialog.getByTestId('method-name').fill(name)
  await dialog.getByTestId('method-description').fill('Pour les clients de la Banque de Tahiti')
  // The type's common text is shown until the method gets its own.
  await expect(dialog).toContainText('texte commun du type')
  await dialog.getByTestId('method-instructions').fill(`Virement à Natimai — ${iban}`)
  await dialog.getByTestId('method-save').click()
  await expect(dialog).toBeHidden()

  const row = page.locator('tr', { hasText: name })
  await expect(row).toContainText('Virement bancaire · instructions propres')

  const shopContext = await browser.newContext({ baseURL: STOREFRONT_URL })
  const shop = await shopContext.newPage()
  try {
    await placeManualOrder(shop, 'manual_transfer', name)
    await expect(shop.getByTestId('checkout-instructions')).toContainText(iban)
  } finally {
    await shopContext.close()
  }

  // Used by an order: it can only be switched off now.
  await page.getByRole('button', { name: 'Actualiser' }).click()
  await row.getByTestId('method-edit').click()
  await expect(dialog.getByTestId('method-delete')).toBeDisabled()
  await dialog.getByText('Proposé aux clients').click()
  await dialog.getByTestId('method-save').click()
  await expect(dialog).toBeHidden()
  await expect(row.locator('.q-toggle').first()).toHaveAttribute('aria-checked', 'false')
})

test('an unused method is deleted', async ({ page }) => {
  const name = `Chèque essai ${Date.now().toString(36)}`
  await loginAdmin(page, '/payment-eligibility')
  await page.getByTestId('method-create').click()
  const dialog = page.getByTestId('method-dialog')
  await dialog.getByTestId('method-type').click()
  await page.getByRole('option', { name: 'Chèque' }).click()
  await dialog.getByTestId('method-name').fill(name)
  await dialog.getByTestId('method-save').click()
  await expect(dialog).toBeHidden()

  const row = page.locator('tr', { hasText: name })
  await row.getByTestId('method-edit').click()
  await dialog.getByTestId('method-delete').click()
  const confirm = page.getByRole('dialog').filter({ hasText: 'Supprimer le moyen de paiement' })
  await confirm.getByRole('button', { name: 'Supprimer' }).click()
  await expect(dialog).toBeHidden()
  await expect(row).toHaveCount(0)
  await expect(page.getByText(`« ${name} » supprimé.`)).toBeVisible()
})
