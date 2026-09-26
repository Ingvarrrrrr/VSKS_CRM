import { test, expect } from '@playwright/test';
import { login, dismissOrgPicker, waitForOverlays, collectApiErrors } from './helpers';

test.describe('VAT/FEO 26.09 verify', () => {
  test('order 912 - single feo category, chip visible', async ({ page }) => {
    const apiErrors = collectApiErrors(page);
    const consoleErrors: string[] = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    await login(page);
    await page.goto('/orders/912');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1500);
    // 27.09: не должно быть глобальной модалки "Ошибка" (см. api.ts::apiFetch
    // dispatch 'api-error' → ApiErrorDialog) — vat-payment-check необязателен
    // для открытия карточки.
    const errorDialog = page.locator('.v-overlay-container').filter({ hasText: 'Ошибка' });
    expect(await errorDialog.count()).toBe(0);
    // 27.09: у каждой позиции закупки — чип категории ФЭО (ItemFeoCategoryChip).
    const chipCount912 = await page.locator('.v-chip:has(.mdi-shape-outline), .v-chip:has(.mdi-lock-outline)').count();
    console.log('ORDER912_FEO_CHIPS', chipCount912);
    expect(chipCount912).toBeGreaterThan(0);
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa2/order-912.png' });
    const itemsBlock912 = page.locator('.summary-row').first();
    if (await itemsBlock912.count()) {
      await page.locator('table').first().screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa2/order-912-items.png' }).catch(() => {});
    }
    console.log('ORDER912_API_ERRORS', JSON.stringify(apiErrors));
    console.log('ORDER912_CONSOLE_ERRORS', JSON.stringify(consoleErrors));
  });

  test('order 899 - multi feo category, header notice', async ({ page }) => {
    const apiErrors = collectApiErrors(page);
    const consoleErrors: string[] = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    await login(page);
    await page.goto('/orders/899');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1500);
    const errorDialog = page.locator('.v-overlay-container').filter({ hasText: 'Ошибка' });
    expect(await errorDialog.count()).toBe(0);
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa2/order-899.png' });
    console.log('ORDER899_API_ERRORS', JSON.stringify(apiErrors));
    console.log('ORDER899_CONSOLE_ERRORS', JSON.stringify(consoleErrors));
  });

  test('order 909 - chips visible', async ({ page }) => {
    await login(page);
    await page.goto('/orders/909');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1500);
    const errorDialog = page.locator('.v-overlay-container').filter({ hasText: 'Ошибка' });
    expect(await errorDialog.count()).toBe(0);
    const chipCount909 = await page.locator('.v-chip:has(.mdi-shape-outline), .v-chip:has(.mdi-lock-outline)').count();
    console.log('ORDER909_FEO_CHIPS', chipCount909);
    expect(chipCount909).toBeGreaterThan(0);
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa/order-909.png', fullPage: true });
  });

  test('order 800 - vat payment mismatch banner + align', async ({ page }) => {
    const apiErrors = collectApiErrors(page);
    await login(page);
    await page.goto('/orders/800');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa/order-800-before.png', fullPage: true });
    const bodyText = await page.textContent('body');
    console.log('ORDER800_HAS_MISMATCH_TEXT', bodyText?.includes('НДС') , bodyText?.includes('7%') || bodyText?.includes('расхожд'));
    console.log('ORDER800_API_ERRORS_BEFORE', JSON.stringify(apiErrors));
  });

  test('payment registry - vat button', async ({ page }) => {
    const apiErrors = collectApiErrors(page);
    await login(page);
    await page.goto('/payments/registry');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa/payments-registry.png', fullPage: true });
    console.log('REGISTRY_API_ERRORS', JSON.stringify(apiErrors));
    console.log('REGISTRY_URL', page.url());
  });

  test('dashboard - apexcharts render', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    await login(page);
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(2500);
    const svgCount = await page.locator('.apexcharts-canvas').count();
    console.log('DASHBOARD_APEXCHARTS_COUNT', svgCount);
    console.log('DASHBOARD_CONSOLE_ERRORS', JSON.stringify(consoleErrors));
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa/dashboard.png', fullPage: true });
  });

  test('plan view - export xlsx', async ({ page }) => {
    await login(page);
    await page.goto('/plan');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1500);
    const downloadPromise = page.waitForEvent('download', { timeout: 10000 }).catch(() => null);
    const exportBtn = page.locator('.v-btn, button').filter({ hasText: /excel|экспорт|xlsx/i }).first();
    const visible = await exportBtn.isVisible().catch(() => false);
    console.log('PLAN_EXPORT_BTN_VISIBLE', visible);
    if (visible) {
      await exportBtn.click({ force: true }).catch(() => {});
      const download = await downloadPromise;
      console.log('PLAN_EXPORT_DOWNLOAD', download ? download.suggestedFilename() : 'NONE');
    }
    await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/qa/plan-view.png', fullPage: true });
  });
});
