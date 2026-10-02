import { expect, test } from '@playwright/test'

import { loginAdmin, openAdmin } from '../../support/admin'
import { LOCALE, STOREFRONT_URL } from '../../support/env'
import { placeTransferOrder } from '../../support/storefront'

/**
 * The back-office side of a manual payment: a customer orders and pays by
 * transfer on the storefront, the payment shows up among the admin's work
 * queues, the admin approves it and the order becomes paid.
 *
 * The last step needs the outbox poller and the ARQ worker running (they turn
 * the approval into the order status change), see e2e/README.md.
 */
test('a transfer is approved from the dashboard and the order becomes paid', async ({
  page,
  browser,
}) => {
  const orderNumber = await test.step('a customer orders and pays by transfer', async () => {
    const shop = await browser.newPage({ baseURL: STOREFRONT_URL, locale: LOCALE })
    try {
      return await placeTransferOrder(shop)
    } finally {
      await shop.close()
    }
  })

  await loginAdmin(page)

  await test.step('the dashboard sends the admin to the payments to validate', async () => {
    await page.getByTestId('todo-payments_to_validate').click()
    await expect(page).toHaveURL(/#\/payment-validations$/)
  })

  const row = page.locator('tr', {
    has: page.getByTestId('payment-order').filter({ hasText: orderNumber }),
  })
  const orderLink = await test.step('the payment is listed with its order number', async () => {
    await expect(row).toHaveCount(1)
    return (await row.getByTestId('payment-order').getAttribute('href')) ?? ''
  })

  await test.step('approving it takes it off the list', async () => {
    await row.getByTestId('payment-approve').click()
    await page.getByTestId('payment-approve-confirm').click()
    await expect(row).toHaveCount(0)
  })

  await test.step('the order becomes paid once the background jobs ran', async () => {
    expect(orderLink).toMatch(/#\/orders\/[0-9a-f-]{36}$/)
    await openAdmin(page, orderLink.slice(orderLink.indexOf('#') + 1))
    await expect(page.getByTestId('page-title')).toHaveText(orderNumber)
    // The approval publishes `payment.captured` to the outbox; the poller hands
    // it to the ARQ worker, which moves the order to Paid. The screen does not
    // poll, so refresh it until the status lands.
    await expect(async () => {
      await page.getByTestId('order-refresh').click()
      await expect(page.getByTestId('order-status')).toHaveText(/Payée/, { timeout: 2_000 })
    }).toPass({ timeout: 60_000 })
  })
})
