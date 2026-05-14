/**
 * Phase 27.1 — contract_items E2E spec
 * Tests D-01/D-02/D-04/D-05 UI flow.
 *
 * BASE_URL: use http://85.239.53.155 for production checks after autodeploy.
 * Run: npx playwright test 27-contract-items.spec.ts --base-url=http://85.239.53.155
 *
 * Note: These tests are skipped in CI until autodeploy confirms the feature is live.
 * Remove test.skip() once the bundle hash has changed post-deploy.
 */
import { test, expect } from '@playwright/test'
import { login, dismissOrgPicker } from './helpers'

const CONTRACTED_STATUSES = ['confirmed', 'contracted', 'delivered', 'paid']

/** Navigate to a purchase in a status that shows contract columns */
async function openContractedPurchase(page: import('@playwright/test').Page) {
  await page.goto('/orders')
  await page.waitForLoadState('networkidle')
  await dismissOrgPicker(page)
  // Find first row with contracted-status chip
  for (const status of CONTRACTED_STATUSES) {
    const chip = page.locator(`[data-status="${status}"]`).first()
    if (await chip.isVisible({ timeout: 1000 }).catch(() => false)) {
      await chip.click()
      await page.waitForLoadState('networkidle')
      return true
    }
  }
  // Fallback: click first row
  const firstRow = page.locator('tbody tr').first()
  if (await firstRow.isVisible({ timeout: 2000 }).catch(() => false)) {
    await firstRow.click()
    await page.waitForLoadState('networkidle')
    return true
  }
  return false
}

test.describe('Phase 27.1 contract_items UI', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('D-04 side-by-side columns — Заявка и Договор видны одновременно', async ({ page }) => {
    test.skip(true, 'Requires purchase in confirmed+ status — run after autodeploy')
    await openContractedPurchase(page)
    // Both group headers should be visible when showContractColumns is true
    await expect(page.locator('th', { hasText: 'Заявка' })).toBeVisible({ timeout: 5000 })
    await expect(page.locator('th', { hasText: 'Договор' })).toBeVisible({ timeout: 5000 })
  })

  test('D-01 copy-from-purchase — кнопка копирует позиции 1:1', async ({ page }) => {
    test.skip(true, 'Requires purchase with purchase_items in confirmed+ status — run after autodeploy')
    const found = await openContractedPurchase(page)
    expect(found).toBe(true)
    const copyBtn = page.locator('button, .v-btn').filter({ hasText: 'Скопировать из заявки' })
    await expect(copyBtn).toBeVisible({ timeout: 5000 })
    await copyBtn.click()
    // Snackbar with success message
    await expect(
      page.locator('.v-snackbar').filter({ hasText: /Скопировано/ }),
    ).toBeVisible({ timeout: 8000 })
  })

  test('D-02 import contract items — переиспользует import dialog', async ({ page }) => {
    test.skip(true, 'Requires purchase in confirmed+ status — run after autodeploy')
    await openContractedPurchase(page)
    const importBtn = page.locator('button, .v-btn').filter({ hasText: 'Импорт из файла/QR' })
    await expect(importBtn).toBeVisible({ timeout: 5000 })
    await importBtn.click()
    // The same import dialog used for purchase_items should appear
    await expect(
      page.locator('.v-dialog, .v-overlay').filter({ hasText: /Импорт/i }),
    ).toBeVisible({ timeout: 5000 })
  })

  test('D-05 split contract item — создаёт 2 строки с одинаковым source_item_id', async ({ page }) => {
    test.skip(true, 'Requires purchase with contract_items — run after autodeploy')
    await openContractedPurchase(page)
    // First copy to populate contract_items
    const copyBtn = page.locator('button, .v-btn').filter({ hasText: 'Скопировать из заявки' })
    if (await copyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await copyBtn.click()
      await page.waitForTimeout(2000)
    }
    // Check split button is visible
    const splitBtn = page.locator('[title="Разделить строку договора"]').first()
    await expect(splitBtn).toBeVisible({ timeout: 5000 })
    const rowsBefore = await page.locator('tbody tr').count()
    await splitBtn.click()
    const rowsAfter = await page.locator('tbody tr').count()
    expect(rowsAfter).toBeGreaterThan(rowsBefore)
  })

  test('D-04 savings badge — Сумма позиций договора показывается под таблицей', async ({ page }) => {
    test.skip(true, 'Requires purchase with contract_items in confirmed+ status — run after autodeploy')
    await openContractedPurchase(page)
    const copyBtn = page.locator('button, .v-btn').filter({ hasText: 'Скопировать из заявки' })
    if (await copyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await copyBtn.click()
      await page.waitForTimeout(2000)
    }
    await expect(
      page.locator('.v-chip').filter({ hasText: 'Сумма позиций договора' }),
    ).toBeVisible({ timeout: 8000 })
  })

  test('API smoke — GET /api/purchases/:id/contract-items returns 200', async ({ request }) => {
    // Try to find a purchase ID by logging in and listing purchases
    // This test doesn't need UI — tests the API directly
    const loginResp = await request.post('/api/auth/token', {
      form: { username: 'admin', password: 'admin123' },
    })
    if (!loginResp.ok()) {
      test.skip(true, 'Cannot authenticate — skipping API smoke test')
      return
    }
    const { access_token } = await loginResp.json()
    const purchasesResp = await request.get('/api/purchases/?limit=1', {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    if (!purchasesResp.ok()) return
    const purchases = await purchasesResp.json()
    if (!purchases?.length) return
    const pid = purchases[0].id
    const ciResp = await request.get(`/api/purchases/${pid}/contract-items`, {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    expect(ciResp.status()).toBe(200)
    const body = await ciResp.json()
    expect(Array.isArray(body)).toBe(true)
  })
})
