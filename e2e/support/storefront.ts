import { expect, type Page } from '@playwright/test'

import { CUSTOMER_EMAIL, CUSTOMER_PASSWORD } from './env'

/**
 * Storefront steps the admin journeys need as a setup (a real order placed the
 * way a customer places it). The page must use the storefront as baseURL.
 */

// The SSR markup is interactive before Vue hydrates it, and hydration resets
// filled inputs, so wait for the app to mount before touching the page.
export async function gotoHydrated(page: Page, path: string) {
  await page.goto(path)
  await page.locator('html[data-hydrated]').waitFor({ state: 'attached' })
}

export async function loginCustomer(page: Page) {
  await gotoHydrated(page, '/connexion')
  await page.getByTestId('login-email').fill(CUSTOMER_EMAIL)
  await page.getByTestId('login-password').fill(CUSTOMER_PASSWORD)
  await page.getByTestId('login-submit').click()
  await expect(page).not.toHaveURL(/connexion/)
}

/**
 * Order the first catalogue product and pay by manual transfer (no gateway):
 * the payment then waits for an admin's validation. Returns the order number
 * (CMD-YYYY-NNNNN) shown on the confirmation.
 */
export async function placeTransferOrder(page: Page): Promise<string> {
  return placeManualOrder(page, 'manual_transfer')
}

/**
 * Same with any manual method (`manual_cash`, `manual_check`,
 * `manual_transfer`). Several methods can share a type: `methodName` picks
 * one by its name, otherwise the first of the type is used. Leaves the
 * customer signed in on the storefront.
 */
export async function placeManualOrder(
  page: Page,
  providerCode: string,
  methodName?: string,
): Promise<string> {
  await loginCustomer(page)
  await gotoHydrated(page, '/catalogue')
  await page.getByTestId('product-add-to-cart').first().click()
  await gotoHydrated(page, '/panier')
  await page.getByTestId('cart-checkout').click()
  await expect(page).toHaveURL(/checkout/)

  await page.locator('[data-testid^="checkout-address-"]').first().click()
  const deliveryOptions = page.locator('[data-testid^="checkout-delivery-"]')
  if ((await deliveryOptions.count()) > 0) await deliveryOptions.first().click()
  const methods = page.getByTestId(`checkout-method-${providerCode}`)
  await (methodName ? methods.filter({ hasText: methodName }) : methods.first()).click()
  // The CGV label holds a link with @click.stop: click the box itself.
  await page.getByTestId('checkout-cgv').locator('.q-checkbox__inner').click()
  await page.getByTestId('checkout-submit').click()

  const reference = page.getByTestId('checkout-order-ref')
  await expect(reference).toHaveText(/CMD-\d{4}-\d{5,}/)
  const match = /CMD-\d{4}-\d{5,}/.exec((await reference.textContent()) ?? '')
  if (!match) throw new Error('No order number on the confirmation')
  return match[0]
}
