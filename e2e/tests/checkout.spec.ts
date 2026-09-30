import { expect, test, type Page } from '@playwright/test'

/**
 * The one journey that must never break: catalogue → cart → checkout → order.
 *
 * Payment goes through the seeded **manual transfer** method, so nothing talks
 * to PayZen: the order is created, an order number is issued (M5) and the
 * customer is shown the transfer instructions. That covers the whole server
 * path — pricing, stock reservation, order creation, numbering — without a
 * gateway in the loop.
 *
 * Data comes from e2e/seed_e2e_data.py; see e2e/README.md.
 */

const CUSTOMER_EMAIL = process.env.E2E_EMAIL ?? 'e2e-customer@example.com'
const CUSTOMER_PASSWORD = process.env.E2E_PASSWORD ?? 'e2e-customer-password-123'

// The SSR markup is interactive before Vue hydrates it, and hydration resets
// filled inputs, so wait for the app to mount before touching the page.
async function gotoHydrated(page: Page, path: string) {
  await page.goto(path)
  await page.locator('html[data-hydrated]').waitFor({ state: 'attached' })
}

async function login(page: Page) {
  await gotoHydrated(page, '/connexion')
  // Quasar forwards fallthrough attributes to the *native* input, not to the
  // q-field wrapper, so the test id already targets the fillable element.
  await page.getByTestId('login-email').fill(CUSTOMER_EMAIL)
  await page.getByTestId('login-password').fill(CUSTOMER_PASSWORD)
  await page.getByTestId('login-submit').click()
  // The app redirects away from /connexion once the token is in memory.
  await expect(page).not.toHaveURL(/connexion/)
}

test('a customer can order from the catalogue and gets an order number', async ({
  page,
}) => {
  await login(page)

  await test.step('catalogue lists purchasable products', async () => {
    await gotoHydrated(page, '/catalogue')
    await expect(page.getByTestId('product-card').first()).toBeVisible()
  })

  await test.step('adding to the cart fills it', async () => {
    // The first orderable item: out-of-stock cards disable their button.
    await page
      .locator('[data-testid="product-add-to-cart"]:not([disabled]):not([aria-disabled="true"])')
      .first()
      .click()
    await gotoHydrated(page, '/panier')
    await expect(page.getByTestId('cart-checkout')).toBeEnabled()
  })

  await test.step('checkout creates the order', async () => {
    await page.getByTestId('cart-checkout').click()
    await expect(page).toHaveURL(/checkout/)

    // Address: the seeded one is preselected, but click it so the test also
    // fails loudly if the list ever comes back empty.
    const address = page.locator('[data-testid^="checkout-address-"]').first()
    await expect(address).toBeVisible()
    await address.click()

    // Delivery mode, when the seeded address has any last-leg option. The
    // submit stays disabled while options exist and none is picked, so this is
    // conditional rather than assumed.
    const deliveryOptions = page.locator('[data-testid^="checkout-delivery-"]')
    if ((await deliveryOptions.count()) > 0) {
      await deliveryOptions.first().click()
    }

    // Manual transfer — no gateway, the response carries instructions.
    const method = page.getByTestId('checkout-method-manual_transfer').first()
    await expect(method).toBeVisible()
    await method.click()

    // Accepting the CGV is mandatory (L1); the submit stays disabled without it.
    await expect(page.getByTestId('checkout-submit')).toBeDisabled()
    // Click the toggle itself, not the row: the label holds a link to the CGV
    // with `@click.stop`, and a centre-of-element click lands on it and is
    // swallowed instead of ticking the box.
    await page.getByTestId('checkout-cgv').locator('.q-checkbox__inner').click()
    await expect(page.getByTestId('checkout-submit')).toBeEnabled()

    await page.getByTestId('checkout-submit').click()
  })

  await test.step('the confirmation shows a sequential order number', async () => {
    const reference = page.getByTestId('checkout-order-ref')
    await expect(reference).toBeVisible()
    // M5 format: CMD-YYYY-NNNNN. A UUID short-ref here would mean the number
    // was never allocated.
    await expect(reference).toHaveText(/Commande CMD-\d{4}-\d{5,}/)
  })
})
