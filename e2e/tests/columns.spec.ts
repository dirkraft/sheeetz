import { test, expect } from './fixtures'

test.describe('Column Configuration', () => {
  test.beforeEach(async ({ page }) => {
    // Reset column settings to defaults
    await page.goto('/sheets')
    await page.evaluate(() =>
      fetch('/api/auth/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ columns: ['filename', 'composer', 'filepath', 'folder', 'source'] }),
      })
    )

    // Scan folder to populate sheets
    await page.goto('/library')
    await page.locator('.scan-btn').click()
    await expect(page.locator('.scan-result')).toBeVisible({ timeout: 10_000 })
    await page.goto('/sheets')
    await expect(page.locator('.result-count')).toBeVisible()
  })

  test('default columns match expected layout', async ({ page }) => {
    const headers = page.locator('.sheets-table thead th:not(.select-col):not(.star-col):not(.star-col)')
    await expect(headers).toHaveCount(5)
    await expect(headers.nth(0)).toContainText('Filename')
    await expect(headers.nth(1)).toContainText('Composer')
    await expect(headers.nth(2)).toContainText('Filepath')
    await expect(headers.nth(3)).toContainText('Folder')
    await expect(headers.nth(4)).toContainText('Source')
  })

  test('column picker opens and shows all columns', async ({ page }) => {
    await page.locator('.columns-btn').click()
    const picker = page.locator('.column-picker')
    await expect(picker).toBeVisible()

    const options = picker.locator('.column-option')
    await expect(options).toHaveCount(10)
  })

  test('toggle column on adds it to the table', async ({ page }) => {
    await page.locator('.columns-btn').click()

    const titleCb = page.locator('.column-option').filter({ hasText: 'Title' }).locator('input[type="checkbox"]')
    await expect(titleCb).not.toBeChecked()
    await titleCb.click({ force: true })
    await expect(titleCb).toBeChecked()

    const headers = page.locator('.sheets-table thead th:not(.select-col):not(.star-col)')
    await expect(headers).toHaveCount(6)
    await expect(page.locator('.sheets-table thead th', { hasText: 'Title' })).toBeVisible()
  })

  test('toggle column off removes it from the table', async ({ page }) => {
    await page.locator('.columns-btn').click()

    const sourceCb = page.locator('.column-option').filter({ hasText: 'Source' }).locator('input[type="checkbox"]')
    await expect(sourceCb).toBeChecked()
    await sourceCb.click({ force: true })
    await expect(sourceCb).not.toBeChecked()

    const headers = page.locator('.sheets-table thead th:not(.select-col):not(.star-col)')
    await expect(headers).toHaveCount(4)
    await expect(page.locator('.sheets-table thead th', { hasText: 'Source' })).not.toBeVisible()
  })

  test('column preferences persist across reload', async ({ page }) => {
    await page.locator('.columns-btn').click()

    // Enable "Genre"
    const genreCb = page.locator('.column-option').filter({ hasText: 'Genre' }).locator('input[type="checkbox"]')
    await genreCb.click({ force: true })
    await expect(genreCb).toBeChecked()

    // Disable "Source"
    const sourceCb = page.locator('.column-option').filter({ hasText: 'Source' }).locator('input[type="checkbox"]')
    await sourceCb.click({ force: true })
    await expect(sourceCb).not.toBeChecked()

    // Wait for save
    await page.waitForTimeout(500)

    // Reload and verify
    await page.reload()
    await expect(page.locator('.result-count')).toBeVisible()

    const headers = page.locator('.sheets-table thead th:not(.select-col):not(.star-col)')
    await expect(headers).toHaveCount(5)
    await expect(page.locator('.sheets-table thead th', { hasText: 'Genre' })).toBeVisible()
    await expect(page.locator('.sheets-table thead th', { hasText: 'Source' })).not.toBeVisible()
  })

  test('cannot disable last remaining column', async ({ page }) => {
    await page.locator('.columns-btn').click()

    // Disable all but Filename
    for (const label of ['Composer', 'Filepath', 'Folder', 'Source']) {
      const cb = page.locator('.column-option').filter({ hasText: label }).locator('input[type="checkbox"]')
      await cb.click({ force: true })
      await expect(cb).not.toBeChecked()
    }

    await expect(page.locator('.sheets-table thead th:not(.select-col):not(.star-col)')).toHaveCount(1)

    // Filename checkbox should be disabled
    const filenameCb = page.locator('.column-option').filter({ hasText: 'Filename' }).locator('input[type="checkbox"]')
    await expect(filenameCb).toBeDisabled()
  })
})
