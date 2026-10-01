import { expect, test, type Page } from '@playwright/test'

/**
 * The catalogue says where an article's stock is and in what condition it is
 * sold, and both are search filters.
 *
 * Seeded by e2e/seed_e2e_data.py: « Station de travail E2E » (new, in our
 * warehouse) and « Portable reconditionné E2E » (refurbished grade A, at the
 * supplier only).
 */

const WAREHOUSE = 'Station de travail E2E'
const SUPPLIER = 'Portable reconditionné E2E'

async function gotoHydrated(page: Page, path: string) {
  await page.goto(path)
  await page.locator('html[data-hydrated]').waitFor({ state: 'attached' })
}

function card(page: Page, name: string) {
  return page.getByTestId('product-card').filter({ hasText: name })
}

test('the catalogue separates our stock from the supplier and new from refurbished', async ({
  page,
}) => {
  await gotoHydrated(page, '/catalogue')

  await test.step('each card says where the stock is and its condition', async () => {
    await page.getByTestId('catalogue-stock-local').check()
    await expect(page).toHaveURL(/stock=local/)
    const warehouse = card(page, WAREHOUSE)
    await expect(warehouse.getByTestId('product-card-stock')).toHaveAttribute(
      'data-source',
      'local',
    )
    await expect(warehouse.getByTestId('product-card-stock')).toContainText(
      'En stock chez nous',
    )
    await expect(warehouse.getByTestId('product-condition')).toHaveText('Neuf')
    await expect(card(page, SUPPLIER)).toHaveCount(0)
  })

  await test.step('the supplier filter lists the supplier-held article', async () => {
    await page.getByTestId('catalogue-stock-supplier').check()
    await expect(page).toHaveURL(/stock=supplier/)
    const supplier = card(page, SUPPLIER)
    await expect(supplier.getByTestId('product-card-stock')).toHaveAttribute(
      'data-source',
      'supplier',
    )
    await expect(supplier).toContainText('En stock chez le fournisseur')
    await expect(supplier).toContainText('Délai de livraison plus long')
    await expect(supplier.getByTestId('product-condition')).toHaveText(
      'Reconditionné · Grade A',
    )
    await expect(card(page, WAREHOUSE)).toHaveCount(0)
  })

  await test.step('the condition filter keeps only refurbished items', async () => {
    await page.getByTestId('catalogue-stock-all').check()
    await page.getByTestId('catalogue-condition-refurbished').check()
    await expect(page).toHaveURL(/cond=refurbished/)
    await expect(card(page, SUPPLIER)).toBeVisible()
    await expect(card(page, WAREHOUSE)).toHaveCount(0)
    await expect(page.getByTestId('product-card').filter({ hasText: 'Neuf' })).toHaveCount(0)
  })

  await test.step('the product page repeats it', async () => {
    await card(page, SUPPLIER).getByRole('link', { name: SUPPLIER }).click()
    await expect(page.getByTestId('product-stock')).toHaveAttribute('data-source', 'supplier')
    await expect(page.getByTestId('product-stock-note')).toContainText('plus long')
    await expect(page.getByTestId('product-condition')).toContainText('Reconditionné')
  })
})
