import { test, expect } from './fixtures'

test.describe('Theme Selector', () => {
  test('switches theme and persists across reload', async ({ page }) => {
    await page.goto('/')

    // Open the theme menu and select dark
    await page.getByLabel('Theme settings').click()
    await expect(page.getByLabel('Dark')).toBeVisible()
    await page.getByLabel('Dark').check()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

    // Reload and verify persistence
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.getByLabel('Theme settings').click()
    await expect(page.getByLabel('Dark')).toBeChecked()
  })
})
