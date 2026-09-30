import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'

/**
 * Providers switched on and off from the admin (R3-P5). PayPal has no
 * credentials in the e2e stack: switched on, it is still not offered to the
 * customers, and the switch survives a reload.
 */
test('an admin switches PayPal on and off', async ({ page }) => {
  await loginAdmin(page, '/payment-eligibility')
  const providers = page.getByTestId('payment-providers')
  const paypal = providers.locator('tr', { hasText: 'PayPal' })
  const toggle = page.getByTestId('provider-enabled-paypal')
  await expect(toggle).toHaveAttribute('aria-checked', 'false')

  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-checked', 'true')
  await expect(paypal).toContainText('Absents')
  await expect(paypal).toContainText('Non proposé')

  await page.reload()
  await expect(page.getByTestId('provider-enabled-paypal')).toHaveAttribute('aria-checked', 'true')

  await page.getByTestId('provider-enabled-paypal').click()
  await expect(page.getByTestId('provider-enabled-paypal')).toHaveAttribute(
    'aria-checked',
    'false',
  )
  // Stripe is announced, not implemented: its switch is locked.
  await expect(page.getByTestId('provider-enabled-stripe')).toHaveAttribute(
    'aria-disabled',
    'true',
  )
})
