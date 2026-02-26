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

  test('metadata edit survives page reload', async ({ page }) => {
    // Wait for viewer to load
    await expect(page.locator('.page-canvas').first()).toBeVisible({ timeout: 15_000 })

    // Capture the URL so we can reload the same sheet
    const sheetUrl = page.url()

    // Open Info panel
    await page.getByRole('button', { name: 'Info' }).click()
    await expect(page.locator('.meta-panel')).toBeVisible()

    // Find the Title input (the editable one, identified by placeholder)
    const titleInput = page.getByRole('textbox', { name: 'Title' })
    await expect(titleInput).toBeVisible()

    // Clear and type a new title
    const newTitle = 'E2E Edited Title ' + Date.now()
    await titleInput.clear()
    await titleInput.fill(newTitle)

    // Save and wait for confirmation
    await page.locator('.save-btn').click()
    await expect(page.locator('.save-ok')).toBeVisible({ timeout: 10_000 })

    // Reload the page completely
    await page.goto(sheetUrl)
    await expect(page.locator('.page-canvas').first()).toBeVisible({ timeout: 15_000 })

    // Re-open Info panel
    await page.getByRole('button', { name: 'Info' }).click()
    await expect(page.locator('.meta-panel')).toBeVisible()

    // Verify the edited title survived the reload
    const reloadedTitleInput = page.getByRole('textbox', { name: 'Title' })
    await expect(reloadedTitleInput).toHaveValue(newTitle)
  })
})
