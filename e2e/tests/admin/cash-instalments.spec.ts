import { expect, test, type Page } from '@playwright/test'

import { loginAdmin, openAdmin } from '../../support/admin'
import { STOREFRONT_URL } from '../../support/env'
import { gotoHydrated, placeManualOrder } from '../../support/storefront'

/**
 * Paying at the office in several times (R3-P2): a customer orders to pay in
 * cash, the admin records a first instalment on the order page, the customer
 * sees what is left, and the rest is recorded at the counter — the order is
 * then paid. Needs the outbox poller and the ARQ worker (see e2e/README.md).
 */

/** « 47 502 F » → 47502 (French grouping uses narrow no-break spaces). */
function amountOf(text: string | null): number {
  return Number((text ?? '').replace(/[^0-9,]/g, '').replace(',', '.'))
}

/** The order page does not poll: refresh until the status lands. */
async function waitForStatus(page: Page, status: RegExp) {
  await expect(async () => {
    await page.getByTestId('order-refresh').click()
    await expect(page.getByTestId('order-status')).toHaveText(status, { timeout: 2_000 })
  }).toPass({ timeout: 60_000 })
}

test('a cash order is paid in two instalments at the office', async ({ page, browser }) => {
  const shopContext = await browser.newContext({ baseURL: STOREFRONT_URL })
  const shop = await shopContext.newPage()
  try {
    const orderNumber = await test.step('the customer orders to pay in cash', () =>
      placeManualOrder(shop, 'manual_cash'))

    await loginAdmin(page, '/payment-validations')
    const row = page.locator('tr', {
      has: page.getByTestId('payment-order').filter({ hasText: orderNumber }),
    })
    await expect(row).toHaveCount(1)
    const orderLink = (await row.getByTestId('payment-order').getAttribute('href')) ?? ''
    const orderId = orderLink.split('/').pop() ?? ''
    await openAdmin(page, orderLink.slice(orderLink.indexOf('#') + 1))
    await expect(page.getByTestId('page-title')).toHaveText(orderNumber)

    const total = amountOf(await page.getByTestId('order-amount-due').textContent())
    expect(total).toBeGreaterThan(1)
    const first = Math.floor(total / 2)

    await test.step('a first instalment leaves the order partly paid', async () => {
      await page.getByTestId('order-payment-receipt').click()
      await page.getByTestId('receipt-amount').fill(String(first))
      await page.getByTestId('receipt-confirm').click()
      await expect
        .poll(async () => amountOf(await page.getByTestId('order-amount-paid').textContent()))
        .toBe(first)
      await waitForStatus(page, /Partiellement payée/)
      expect(amountOf(await page.getByTestId('order-amount-due').textContent())).toBe(total - first)
    })

    await test.step('the customer sees what is left to pay', async () => {
      await gotoHydrated(shop, `/mon-compte/commandes/${orderId}`)
      const partial = shop.getByTestId('order-partial')
      await expect(partial).toBeVisible()
      await expect(partial).toContainText('Reste à régler')
    })

    await test.step('the rest, recorded at the counter, pays the order', async () => {
      await page.getByTestId('order-counter-payment').click()
      // The dialog proposes exactly what is left.
      await expect(page.getByTestId('receipt-amount')).toHaveValue(String(total - first))
      await page.getByTestId('receipt-confirm').click()
      await waitForStatus(page, /Payée/)
      expect(amountOf(await page.getByTestId('order-amount-due').textContent())).toBe(0)
      await expect(page.getByTestId('order-receipts').locator('tbody tr')).toHaveCount(2)
    })
  } finally {
    await shopContext.close()
  }
})
