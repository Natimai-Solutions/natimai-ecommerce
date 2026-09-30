import { expect, test } from '@playwright/test'

import { gotoHydrated, loginCustomer } from '../support/storefront'

/**
 * Back from PayPal without paying: the return page says so and never waits for
 * a bank answer (nothing is captured, the order stays awaiting payment).
 */
test('a customer who cancels on PayPal is told nothing was charged', async ({ page }) => {
  await loginCustomer(page)
  const paymentId = '00000000-0000-4000-8000-000000000000'
  await gotoHydrated(page, `/paiement/retour?payment=${paymentId}&provider=paypal&cancelled=1`)

  await expect(page.getByTestId('payment-cancelled')).toContainText("rien n'a été débité")
  await expect(page.getByRole('heading', { name: 'Paiement annulé' })).toBeVisible()
})
