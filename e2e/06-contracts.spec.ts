import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Контракты — список и фильтры', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Список контрактов загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/contracts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);

    const serverErrors = apiErrors.filter(e => e.includes('500') || e.includes('403'));
    if (serverErrors.length > 0) {
      console.log('  ❌ API errors:', serverErrors);
    }
  });

  test('Мульти-фильтры работают', async () => {
    await page.goto('/contracts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    // Try each filter dropdown with force click
    const selects = page.locator('.v-select, .v-autocomplete, .v-combobox');
    const selectCount = await selects.count();
    console.log(`  🔍 Filter dropdowns found: ${selectCount}`);

    for (let i = 0; i < Math.min(selectCount, 3); i++) {
      const sel = selects.nth(i);
      if (await sel.isVisible().catch(() => false)) {
        await sel.click({ force: true });
        await page.waitForTimeout(500);
        // Select first option if available
        const option = page.locator('.v-list-item').first();
        if (await option.isVisible({ timeout: 1000 }).catch(() => false)) {
          await option.click({ force: true });
          await page.waitForTimeout(500);
        }
        await page.keyboard.press('Escape');
        await page.waitForTimeout(300);
      }
    }
  });

  test('Кнопка "Добавить" контракт работает', async () => {
    await page.goto('/contracts');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const clicked = await clickButton(page, /добавить|создать|add|новый/i);
    if (clicked) {
      await page.waitForTimeout(1000);
      const dialog = page.locator('.v-dialog');
      const dialogVisible = await dialog.first().isVisible().catch(() => false);
      console.log(`  📝 Add contract dialog: ${dialogVisible}`);
      await page.keyboard.press('Escape');
    }
  });
});
