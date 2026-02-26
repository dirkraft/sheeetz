import { test, expect } from './fixtures'

test.describe('Sheets', () => {
  test.beforeEach(async ({ page }) => {
    // Scan folder to populate sheets
    await page.goto('/library')
    await page.locator('.scan-btn').click()
    await expect(page.locator('.scan-result')).toBeVisible({ timeout: 10_000 })
  })

  test('lists sheets after scan', async ({ page }) => {
    await page.goto('/sheets')
    await expect(page.locator('.result-count')).toContainText('2 sheets found')
    await expect(page.getByText('sample.pdf')).toBeVisible()
    await expect(page.getByText('nested.pdf')).toBeVisible()
  })

  test('filter by filename', async ({ page }) => {
    await page.goto('/sheets')
    await expect(page.locator('.result-count')).toContainText('2 sheets')

    await page.getByPlaceholder('Search by filename').fill('sample')
    await expect(page.locator('.result-count')).toContainText('1 sheet found')
    await expect(page.getByText('sample.pdf')).toBeVisible()
  })

  test('clear filter restores all', async ({ page }) => {
    await page.goto('/sheets')
    await page.getByPlaceholder('Search by filename').fill('sample')
    await expect(page.locator('.result-count')).toContainText('1 sheet')

    await page.getByPlaceholder('Search by filename').clear()
    await expect(page.locator('.result-count')).toContainText('2 sheets')
  })

  test('click row navigates to viewer', async ({ page }) => {
    await page.goto('/sheets')
    await page.locator('.sheet-row').first().click()
    await expect(page).toHaveURL(/\/sheets\/\d+/)
  })
})
