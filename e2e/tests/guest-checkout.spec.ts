import { expect, test } from '@playwright/test'

import { CUSTOMER_EMAIL } from '../support/env'
import { gotoHydrated } from '../support/storefront'

/**
 * « Commande sans compte » : a visitor orders with an e-mail, a name and an
 * address typed in the checkout, then is offered the link that sets a
 * password. A known address never opens a session.
 */

async function fillCartAndOpenCheckout(page: import('@playwright/test').Page) {
  await gotoHydrated(page, '/catalogue')
  await page
    .locator('[data-testid="product-add-to-cart"]:not([disabled]):not([aria-disabled="true"])')
    .first()
    .click()
  await gotoHydrated(page, '/panier')
  await page.getByTestId('cart-checkout').click()
  await expect(page).toHaveURL(/checkout/)
}

test('a visitor orders without an account', async ({ page }) => {
  await fillCartAndOpenCheckout(page)

  await test.step('identify with an e-mail', async () => {
    await page.getByTestId('guest-email').fill(`invite-${Date.now()}@example.com`)
    await page.getByTestId('guest-name').fill('Hina Teriitahi')
    await page.getByTestId('guest-submit').click()
  })

  await test.step('the address is asked in the checkout', async () => {
    const postal = page.getByTestId('address-postal')
    await expect(postal).toBeVisible()
    await postal.fill('98713')
    await page.keyboard.press('Escape')
    await page.getByTestId('address-city').fill('Papeete')
    await page.getByTestId('address-street').fill('12 rue des Écoles')
    await page.getByTestId('address-save').click()
    await expect(page.locator('[data-testid^="checkout-address-"]')).toHaveCount(1)
  })

  await test.step('order and get the offer to keep an account', async () => {
    const deliveryOptions = page.locator('[data-testid^="checkout-delivery-"]')
    if ((await deliveryOptions.count()) > 0) await deliveryOptions.first().click()
    await page.getByTestId('checkout-method-manual_transfer').first().click()
    await page.getByTestId('checkout-cgv').locator('.q-checkbox__inner').click()
    await page.getByTestId('checkout-submit').click()
    await expect(page.getByTestId('checkout-order-ref')).toHaveText(/CMD-\d{4}-\d{5,}/)

    await page.getByTestId('guest-offer-send').click()
    await expect(page.getByTestId('guest-offer')).toContainText('lien vient')
  })
})

test('a known address is asked to sign in', async ({ page }) => {
  await fillCartAndOpenCheckout(page)
  await page.getByTestId('guest-email').fill(CUSTOMER_EMAIL)
  await page.getByTestId('guest-name').fill('Quelqu’un')
  await page.getByTestId('guest-submit').click()
  await expect(page.getByTestId('guest-form')).toContainText('connectez-vous')
  await expect(page.locator('[data-testid^="checkout-address-"]')).toHaveCount(0)
})
