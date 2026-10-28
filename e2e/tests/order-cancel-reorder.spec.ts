import { expect, test } from '@playwright/test'

import { gotoHydrated, placeTransferOrder } from '../support/storefront'

/**
 * From « Mes commandes », the customer cancels an order that received no money
 * (a transfer not made yet) and puts its articles back into the cart.
 */
test('an unpaid order is cancelled and ordered again', async ({ page }) => {
  const reference = await placeTransferOrder(page)

  await gotoHydrated(page, '/mon-compte?tab=orders')
  const row = page.locator('.order-row', { hasText: reference })
  await row.getByRole('link', { name: 'Détail' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(reference)

  await test.step('order again: the articles come back to the cart', async () => {
    await page.getByTestId('order-reorder').click()
    await expect(page.getByTestId('order-action-notice')).toContainText('panier')
  })

  await test.step('cancel after confirming', async () => {
    await page.getByTestId('order-cancel').click()
    await page.getByTestId('order-cancel-confirm').click()
    await expect(page.getByTestId('order-action-notice')).toContainText('Commande annulée')
    await expect(page.getByText('Annulée', { exact: true })).toBeVisible()
    // Cancelled once and for all: the button is gone.
    await expect(page.getByTestId('order-cancel')).toHaveCount(0)
  })
})
