import { expect, test } from '@playwright/test'

import { gotoHydrated } from '../support/storefront'

/**
 * The header search: suggestions while typing, accents ignored, and a typo
 * still finds the article (« résultats approchants »).
 */
test('the search suggests articles, accents and typos included', async ({ page }) => {
  await gotoHydrated(page, '/catalogue')
  const field = page.locator('#header-search')

  await test.step('no accent typed, the accented name is suggested', async () => {
    await field.fill('reconditionne')
    const suggestions = page.getByTestId('search-suggestions')
    await expect(suggestions.getByRole('option').first()).toContainText('reconditionné')
  })

  await test.step('a typo still finds the article, flagged as approximate', async () => {
    await field.fill('statoin')
    await field.press('Enter')
    await expect(page).toHaveURL(/q=statoin/)
    await expect(page.getByTestId('catalogue-approximate')).toBeVisible()
    await expect(page.getByText('Station de travail E2E')).toBeVisible()
  })
})
