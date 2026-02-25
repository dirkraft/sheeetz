import { test, expect } from './fixtures'

test.describe('Admin', () => {
  test('clear index removes all sheets', async ({ page }) => {
    // Ensure sheets exist by scanning
    await page.goto('/library')
    await page.locator('.scan-btn').click()
    await expect(page.locator('.scan-result')).toBeVisible({ timeout: 10_000 })

    // Verify sheets exist
    await page.goto('/sheets')
    await expect(page.locator('.result-count')).toContainText('2 sheets')

    // Go to admin and clear
    await page.goto('/admin')
    page.on('dialog', dialog => dialog.accept())
    await page.locator('.danger-btn').click()

    await expect(page.locator('.success')).toBeVisible()
    await expect(page.locator('.success')).toContainText('Cleared')

    // Verify sheets are gone
    await page.goto('/sheets')
    // Wait for load to finish — either empty state or 0 results
    await expect(page.locator('.empty')).toBeVisible({ timeout: 10_000 })
  })
})
