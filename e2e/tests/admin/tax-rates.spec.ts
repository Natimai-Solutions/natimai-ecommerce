import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'

/**
 * VAT rates are the shop's own: the Polynesian set (16 / 13 / 5 / 0 %) is
 * seeded under « TVA », and the admin chooses which rate applies by default
 * and which one taxes the fees — here switched and switched back.
 */
test('the admin chooses the default and fees VAT rates', async ({ page }) => {
  await loginAdmin(page, '/tax-rates')
  await expect(page.getByRole('cell', { name: 'TVA taux intermédiaire' })).toBeVisible()

  const fees = page.getByTestId('tax-fees-code')
  await expect(page.getByTestId('tax-default-code')).toHaveValue('TVA taux normal — 16 %')
  await expect(fees).toHaveValue('TVA taux normal — 16 %')

  await fees.click()
  await page.getByRole('option', { name: 'TVA taux intermédiaire — 13 %' }).click()
  await page.getByTestId('tax-settings-save').click()
  await expect(page.getByText('Taux enregistrés.')).toBeVisible()

  await page.reload()
  await expect(page.getByTestId('tax-fees-code')).toHaveValue('TVA taux intermédiaire — 13 %')

  await page.getByTestId('tax-fees-code').click()
  await page.getByRole('option', { name: 'TVA taux normal — 16 %' }).click()
  await page.getByTestId('tax-settings-save').click()
  await expect(page.getByText('Taux enregistrés.')).toBeVisible()
})
