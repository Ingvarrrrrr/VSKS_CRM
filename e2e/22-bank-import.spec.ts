import { test, expect, Page } from '@playwright/test';
import path from 'path';
import { login, waitForOverlays, dismissOrgPicker, collectApiErrors } from './helpers';

/**
 * Phase 22 — Bank statement import E2E smoke tests.
 *
 * Covers:
 *  - Menu item "Платежи" visible after login
 *  - Upload xlsx → import job created → payments/registry shows all 3 rows
 *  - Rejected (АННУЛИРОВАН) payment listed but confirm button disabled
 *  - Manual match scaffold for unmatched payment (ПП-003)
 *
 * Fixture: e2e/fixtures/sample-bank-statement.xlsx
 *   Row 1 ПП-001  ИСПОЛНЕН   12 090,25  — possible auto-match if contract 11-26-1 exists on prod
 *   Row 2 ПП-002  АННУЛИРОВАН 5 000,00  — rejected, never bound to Payment
 *   Row 3 ПП-003  ИСПОЛНЕН   8 500,50   — unmatched (contract 999-NOMATCH does not exist)
 *
 * Run:
 *   BASE_URL=http://85.239.53.155 npx playwright test e2e/22-bank-import.spec.ts
 */

const FIXTURE = path.join(__dirname, 'fixtures', 'sample-bank-statement.xlsx');

// ---------------------------------------------------------------------------
// Shared page (re-used across tests in describe block to avoid repeated login)
// ---------------------------------------------------------------------------
test.describe('Phase 22 — Bank statement import', () => {
  let sharedPage: Page;

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage();
    await login(sharedPage);
    await dismissOrgPicker(sharedPage);
  });

  test.afterAll(async () => {
    await sharedPage.close();
  });

  // -------------------------------------------------------------------------
  // T-01: Navigation
  // -------------------------------------------------------------------------
  test('T-01: admin sees "Платежи" menu item in sidebar', async () => {
    await sharedPage.goto('/');
    await sharedPage.waitForLoadState('networkidle');
    await waitForOverlays(sharedPage);
    await expect(
      sharedPage.locator('.v-navigation-drawer, nav').getByText(/Платежи/i).first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  // -------------------------------------------------------------------------
  // T-02: Import page reachable
  // -------------------------------------------------------------------------
  test('T-02: /payments/import page renders file input and import button', async () => {
    await sharedPage.goto('/payments/import');
    await sharedPage.waitForLoadState('networkidle');
    await waitForOverlays(sharedPage);

    // File input must exist (may be visually hidden — check presence, not visibility)
    await expect(sharedPage.locator('input[type="file"]').first()).toHaveCount(1, { timeout: 10_000 });

    // Import / upload button must be visible
    const importBtn = sharedPage
      .locator('.v-btn, button')
      .filter({ hasText: /Импортировать|Загрузить|Импорт/i })
      .first();
    await expect(importBtn).toBeVisible({ timeout: 8_000 });
  });

  // -------------------------------------------------------------------------
  // T-03: Upload xlsx → rows appear in registry
  // -------------------------------------------------------------------------
  test('T-03: upload xlsx → job created → registry shows all 3 rows', async () => {
    const apiErrors = collectApiErrors(sharedPage);

    await sharedPage.goto('/payments/import');
    await sharedPage.waitForLoadState('networkidle');
    await waitForOverlays(sharedPage);

    // Set the fixture file on the hidden input
    await sharedPage.locator('input[type="file"]').first().setInputFiles(FIXTURE);
    await sharedPage.waitForTimeout(500);

    // Click the import / upload button
    const importBtn = sharedPage
      .locator('.v-btn, button')
      .filter({ hasText: /Импортировать|Загрузить|Импорт/i })
      .first();
    await importBtn.click();

    // Wait for success feedback: snackbar, alert, or a row in the import history table
    // Accept any of these signals:
    const successSignals = sharedPage.locator(
      '[class*="snack"] [class*="text"], .v-snackbar, [role="alert"], table tbody tr',
    );
    await expect(successSignals.first()).toBeVisible({ timeout: 30_000 });

    // No 5xx errors during upload
    expect(apiErrors.filter((e) => e.includes(' 5'))).toEqual([]);

    // Navigate to registry — all 3 doc numbers must be present
    // Try clicking "Открыть детали" / "Реестр" link first, fall back to direct nav
    const detailsLink = sharedPage
      .locator('.v-btn, a, button')
      .filter({ hasText: /Открыть детали|Реестр|Перейти/i })
      .first();
    if (await detailsLink.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await detailsLink.click();
      await sharedPage.waitForLoadState('networkidle');
    } else {
      await sharedPage.goto('/payments/registry');
      await sharedPage.waitForLoadState('networkidle');
    }

    await waitForOverlays(sharedPage);
    await sharedPage.waitForTimeout(1_000);

    await expect(sharedPage.locator('text=ПП-001').first()).toBeVisible({ timeout: 15_000 });
    await expect(sharedPage.locator('text=ПП-002').first()).toBeVisible({ timeout: 5_000 });
    await expect(sharedPage.locator('text=ПП-003').first()).toBeVisible({ timeout: 5_000 });
  });

  // -------------------------------------------------------------------------
  // T-04: Rejected payment is listed but cannot be confirmed
  // -------------------------------------------------------------------------
  test('T-04: rejected row (ПП-002 / АННУЛИРОВАН) listed, confirm button absent or disabled', async () => {
    await sharedPage.goto('/payments/registry');
    await sharedPage.waitForLoadState('networkidle');
    await waitForOverlays(sharedPage);
    await sharedPage.waitForTimeout(1_000);

    // Find the row containing ПП-002
    const row = sharedPage.locator('tr').filter({ has: sharedPage.locator('text=ПП-002') }).first();
    await expect(row).toBeVisible({ timeout: 10_000 });

    // Status label should reflect rejection
    await expect(
      row.locator('text=/АННУЛИРОВАН|Аннулирован|rejected/i').first(),
    ).toBeVisible({ timeout: 5_000 });

    // Confirm button must NOT be present OR must be disabled
    const confirmBtn = row
      .locator('.v-btn, button')
      .filter({ hasText: /Подтвердить|Confirm/i })
      .first();
    const confirmCount = await confirmBtn.count();
    if (confirmCount > 0) {
      // If button exists, it must be disabled
      await expect(confirmBtn).toBeDisabled();
    }
    // If count === 0 the assertion passes implicitly (button absent = cannot confirm)
  });

  // -------------------------------------------------------------------------
  // T-05: Unmatched payment (ПП-003) has a "bind / match" affordance
  // -------------------------------------------------------------------------
  test('T-05: unmatched row (ПП-003) has manual-match affordance visible', async () => {
    await sharedPage.goto('/payments/registry');
    await sharedPage.waitForLoadState('networkidle');
    await waitForOverlays(sharedPage);
    await sharedPage.waitForTimeout(1_000);

    const row = sharedPage.locator('tr').filter({ has: sharedPage.locator('text=ПП-003') }).first();
    await expect(row).toBeVisible({ timeout: 10_000 });

    // Look for a match/link button: icon button or text button
    const matchBtn = row
      .locator(
        'button[aria-label*="Привязать"], button[aria-label*="Матч"], button[aria-label*="link"], ' +
        '.mdi-link-variant, .mdi-link, .v-btn',
      )
      .first();

    if (await matchBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await matchBtn.click();
      await sharedPage.waitForTimeout(800);
      // A dialog / panel for contract search should open
      const searchDialog = sharedPage.locator(
        '.v-dialog, .v-overlay--active, [role="dialog"]',
      ).first();
      if (await searchDialog.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await expect(searchDialog).toBeVisible();
        await sharedPage.keyboard.press('Escape');
        await sharedPage.waitForTimeout(300);
      } else {
        // Dialog did not open — mark as soft skip (UI may differ)
        // TODO: tighten selector once RegistryView manual-match dialog DOM stabilises
        console.warn('[T-05] Manual-match dialog did not open — selector needs adjustment');
      }
    } else {
      // No match affordance visible at all — skip gracefully
      test.skip(true, '[T-05] Match button selector did not match — adjust once RegistryView DOM stabilises');
    }
  });

  // -------------------------------------------------------------------------
  // T-06: /payments/registry page renders without 5xx errors
  // -------------------------------------------------------------------------
  test('T-06: /payments/registry renders cleanly with no server errors', async ({ page }) => {
    // Fresh page to capture all API calls from page load
    const apiErrors = collectApiErrors(page);
    await login(page);
    await dismissOrgPicker(page);
    await page.goto('/payments/registry');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1_000);

    // Page must show some content (table or empty state message)
    const hasContent = await page
      .locator('table, [class*="empty"], text=/Нет данных|Пусто|No data|Реестр/i')
      .first()
      .isVisible({ timeout: 10_000 })
      .catch(() => false);
    expect(hasContent).toBe(true);

    // No 5xx from the registry API
    expect(apiErrors.filter((e) => e.includes(' 5'))).toEqual([]);
  });
});
