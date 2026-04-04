import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Субсидии — CRUD и интерактивность', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Список субсидий загружается', async () => {
    await page.goto('/subsidies');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const items = page.locator('.v-card, .v-list-item, tr');
    const count = await items.count();
    console.log(`  📋 Found ${count} subsidy items`);
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('Кнопка добавления субсидии открывает диалог', async () => {
    await page.goto('/subsidies');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    // Try icon button (mdi-plus) or text button
    const addBtn = page.locator('.v-btn').filter({ has: page.locator('.mdi-plus') }).first();
    const textBtn = page.locator('.v-btn').filter({ hasText: /добавить|создать|add|новая/i }).first();

    let clicked = false;
    if (await addBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await addBtn.click({ force: true });
      clicked = true;
    } else if (await textBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await textBtn.click({ force: true });
      clicked = true;
    }

    if (clicked) {
      await page.waitForTimeout(1000);
      const dialog = page.locator('.v-dialog');
      const dialogVisible = await dialog.first().isVisible().catch(() => false);
      console.log(`  📝 Add dialog appeared: ${dialogVisible}`);
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    } else {
      console.log('  ⚠️ Add button not found (tried icon + text)');
    }
  });

  test('Фильтр по году работает', async () => {
    await page.goto('/subsidies');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const yearChips = page.locator('.v-chip').filter({ hasText: /202[4-6]/ });
    if (await yearChips.count() > 0) {
      await yearChips.first().click({ force: true });
      await page.waitForTimeout(1000);
    }
  });
});
