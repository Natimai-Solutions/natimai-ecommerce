import { expect, test } from '@playwright/test'

import { loginAdmin } from '../../support/admin'
import { STOREFRONT_URL } from '../../support/env'

/**
 * Homepage blocks cross the two apps: a banner published from the admin shows
 * on the storefront homepage, and disappears once deleted.
 */
test('a banner published from the admin shows on the storefront until deleted', async ({
  page,
  browser,
}) => {
  const title = `Bannière e2e ${Date.now()}`
  await loginAdmin(page, '/homepage')

  const block = page.getByTestId('homepage-block').filter({ hasText: title })

  await test.step('the admin publishes a banner', async () => {
    await page.getByTestId('homepage-new').click()
    await page.getByTestId('homepage-title').fill(title)
    await page.getByTestId('homepage-published').click()
    await page.getByTestId('homepage-save').click()
    await expect(block).toHaveCount(1)
  })

  const shop = await browser.newPage({ baseURL: STOREFRONT_URL })
  try {
    await test.step('the storefront homepage shows it', async () => {
      await shop.goto('/')
      await expect(shop.getByTestId('home-banners')).toContainText(title)
    })

    await test.step('deleting it removes it from the storefront', async () => {
      await block.getByTestId('homepage-delete').click()
      await expect(block).toHaveCount(0)
      await shop.reload()
      await expect(shop.getByText(title)).toHaveCount(0)
    })
  } finally {
    await shop.close()
  }
})
