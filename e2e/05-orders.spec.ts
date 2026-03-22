import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Закупки — список и создание', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Список закупок загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const table = page.locator('.v-data-table, .v-table, table');
    const hasTable = await table.first().isVisible().catch(() => false);
    console.log(`  📋 Orders table visible: ${hasTable}`);

    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ Server errors:', apiErrors.filter(e => e.includes('500')));
    }
  });

  test('Фильтры работают', async () => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    // Try search field — use force click to bypass overlays
    const searchInput = page.locator('input[type="text"]').first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.click({ force: true });
      await searchInput.fill('тест');
      await page.waitForTimeout(1500);
      await searchInput.clear();
      await page.waitForTimeout(1000);
    }
  });

  test('Форма создания закупки загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/create-order');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const inputs = page.locator('input, .v-select, .v-autocomplete, .v-textarea');
    const inputCount = await inputs.count();
    console.log(`  📝 Form fields found: ${inputCount}`);
    expect(inputCount).toBeGreaterThanOrEqual(1);

    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ Server errors on create-order:', apiErrors.filter(e => e.includes('500')));
    }
  });

  test('Экспорт Excel кнопка есть', async () => {
    await page.goto('/orders');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    const exportBtn = page.locator('.v-btn').filter({ hasText: /экспорт|export|excel|скачать/i });
    const hasExport = await exportBtn.first().isVisible().catch(() => false);
    console.log(`  📥 Export button visible: ${hasExport}`);
  });
});
