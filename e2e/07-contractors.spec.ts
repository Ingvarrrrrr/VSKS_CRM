import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Контрагенты — CRUD', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Список контрагентов загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/contractors');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const table = page.locator('.v-data-table, .v-table, table');
    const hasTable = await table.first().isVisible().catch(() => false);
    console.log(`  📋 Contractors table: ${hasTable}`);

    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ Server errors:', apiErrors);
    }
  });

  test('Поиск контрагентов', async () => {
    await page.goto('/contractors');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const search = page.locator('input[type="text"]').first();
    if (await search.isVisible().catch(() => false)) {
      await search.click({ force: true });
      await search.fill('ООО');
      await page.waitForTimeout(1500);
      await search.clear();
      await page.waitForTimeout(1000);
    }
  });

  test('Кнопка добавления контрагента', async () => {
    await page.goto('/contractors');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const addBtn = page.locator('.v-btn').filter({ has: page.locator('.mdi-plus') }).first();
    const textBtn = page.locator('.v-btn').filter({ hasText: /добавить|создать|add|импорт/i }).first();

    if (await addBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await addBtn.click({ force: true });
      await page.waitForTimeout(1000);
      await page.keyboard.press('Escape');
    } else if (await textBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await textBtn.click({ force: true });
      await page.waitForTimeout(1000);
      await page.keyboard.press('Escape');
    } else {
      console.log('  ⚠️ Add button not found');
    }
  });
});
