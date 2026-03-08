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
    await expect(page.locator('.sheet-row', { hasText: 'sample.pdf' })).toHaveCount(1)
    await expect(page.locator('.sheet-row', { hasText: 'nested.pdf' })).toHaveCount(1)
    await expect(page.getByRole('columnheader', { name: 'Filepath' })).toBeVisible()
    await expect(page.getByRole('cell', { name: 'subfolder/nested.pdf', exact: true })).toBeVisible()
  })

  test('filter by filename', async ({ page }) => {
    await page.goto('/sheets')
    await expect(page.locator('.result-count')).toContainText('2 sheets')

    await page.getByPlaceholder('Search sheets...').fill('sample')
    await expect(page.locator('.result-count')).toContainText('1 sheet found')
    await expect(page.locator('.sheet-row', { hasText: 'sample.pdf' })).toHaveCount(1)
  })

  test('clear filter restores all', async ({ page }) => {
    await page.goto('/sheets')
    await page.getByPlaceholder('Search sheets...').fill('sample')
    await expect(page.locator('.result-count')).toContainText('1 sheet')

    await page.getByPlaceholder('Search sheets...').clear()
    await expect(page.locator('.result-count')).toContainText('2 sheets')
  })

  test('click row navigates to viewer', async ({ page }) => {
    await page.goto('/sheets')
    await page.locator('.sheet-row').first().click()
    await expect(page).toHaveURL(/\/sheets\/\d+/)
  })
})
