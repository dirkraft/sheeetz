import { test, expect } from './fixtures'

test.describe('Sheet Viewer', () => {
  test.beforeEach(async ({ page }) => {
    // Scan to populate sheets
    await page.goto('/library')
    await page.locator('.scan-btn').click()
    await expect(page.locator('.scan-result')).toBeVisible({ timeout: 10_000 })

    // Navigate to first sheet
    await page.goto('/sheets')
    await page.locator('.sheet-row').first().click()
    await expect(page).toHaveURL(/\/sheets\/\d+/)
  })

  test('viewer renders canvas', async ({ page }) => {
    // Wait for loading to finish and canvas to appear
    await expect(page.locator('.page-canvas').first()).toBeVisible({ timeout: 15_000 })
  })

  test('shows filename in toolbar', async ({ page }) => {
    await expect(page.locator('.title')).toBeVisible({ timeout: 10_000 })
    const title = await page.locator('.title').textContent()
    expect(title).toMatch(/\.pdf$/)
  })

  test('shows page info', async ({ page }) => {
    await expect(page.locator('.page-info')).toBeVisible({ timeout: 10_000 })
    const info = await page.locator('.page-info').textContent()
    expect(info).toMatch(/\d+/)
  })
})
