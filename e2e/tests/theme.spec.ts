import { test, expect } from './fixtures'

test.describe('Theme Selector', () => {
  test('switches theme and persists across reload', async ({ page }) => {
    await page.goto('/')

    const themeSelect = page.getByLabel('Theme')
    await expect(themeSelect).toBeVisible()

    await themeSelect.selectOption('dark')
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

    await page.reload()
    await expect(themeSelect).toHaveValue('dark')
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  })
})
