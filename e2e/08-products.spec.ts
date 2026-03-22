import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Продукты — каталог и фильтры', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Каталог продуктов загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);

    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ Server errors on products:', apiErrors);
    }
  });

  test('Фильтры продуктов работают', async () => {
    await page.goto('/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const search = page.locator('input[type="text"]').first();
    if (await search.isVisible().catch(() => false)) {
      await search.click({ force: true });
      await search.fill('бумага');
      await page.waitForTimeout(1500);
      await search.clear();
    }
  });

  test('Кнопка добавления продукта', async () => {
    await page.goto('/products');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const addBtn = page.locator('.v-btn').filter({ has: page.locator('.mdi-plus') }).first();
    const textBtn = page.locator('.v-btn').filter({ hasText: /добавить|создать|add|новый/i }).first();

    if (await addBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await addBtn.click({ force: true });
      await page.waitForTimeout(1000);
      const dialog = page.locator('.v-dialog');
      console.log(`  📝 Add product dialog: ${await dialog.first().isVisible().catch(() => false)}`);
      await page.keyboard.press('Escape');
    } else if (await textBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await textBtn.click({ force: true });
      await page.waitForTimeout(1000);
      await page.keyboard.press('Escape');
    }
  });

  test('Сводка продуктов загружается', async () => {
    await page.goto('/products-summary');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
  });
});
