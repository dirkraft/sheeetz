import { test, expect } from './fixtures'

test.describe('Library', () => {
  test('shows seeded folder', async ({ page }) => {
    await page.goto('/library')
    await expect(page.locator('.folder-item')).toHaveCount(1)
    await expect(page.getByText('fixtures', { exact: true })).toBeVisible()
  })

  test('scan folder finds PDFs', async ({ page }) => {
    // Clear index first to ensure clean state
    await page.goto('/admin')
    page.on('dialog', dialog => dialog.accept())
    await page.locator('.danger-btn').click()
    await expect(page.locator('.success')).toBeVisible()

    await page.goto('/library')
    const scanBtn = page.locator('.scan-btn')
    await expect(scanBtn).toBeVisible()
    await scanBtn.click()

    const result = page.locator('.scan-result')
    await expect(result).toBeVisible({ timeout: 10_000 })
    await expect(result).toContainText('2 new')
    await expect(result).toContainText('2 total PDFs')
  })

  test('re-scan shows 0 new', async ({ page }) => {
    // Clear and scan fresh
    await page.goto('/admin')
    page.on('dialog', dialog => dialog.accept())
    await page.locator('.danger-btn').click()
    await expect(page.locator('.success')).toBeVisible()

    await page.goto('/library')
    const scanBtn = page.locator('.scan-btn')
    await scanBtn.click()
    await expect(page.locator('.scan-result')).toContainText('2 new')

    // Second scan
    await scanBtn.click()
    await expect(page.locator('.scan-result')).toContainText('0 new')
    await expect(page.locator('.scan-result')).toContainText('2 total PDFs')
  })
})
