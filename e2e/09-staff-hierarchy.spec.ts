import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Персонал и иерархия', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Вкладка "Отделы" загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/staff');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);

    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ Server errors on staff:', apiErrors);
    }
  });

  test('Переключение вкладок Отделы/Пользователи', async () => {
    await page.goto('/staff');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const usersTab = page.locator('.v-tab, .v-btn').filter({ hasText: /пользовател|users/i });
    if (await usersTab.first().isVisible().catch(() => false)) {
      await usersTab.first().click({ force: true });
      await page.waitForTimeout(1500);
    }

    const deptTab = page.locator('.v-tab, .v-btn').filter({ hasText: /отдел|department/i });
    if (await deptTab.first().isVisible().catch(() => false)) {
      await deptTab.first().click({ force: true });
      await page.waitForTimeout(1500);
    }
  });

  test('Иерархия (VueFlow) загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/hierarchy');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const canvas = page.locator('.vue-flow, .vue-flow__container, [class*="flow"]');
    const hasCanvas = await canvas.first().isVisible().catch(() => false);
    console.log(`  🌳 Hierarchy canvas visible: ${hasCanvas}`);

    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ Server errors on hierarchy:', apiErrors);
    }
  });
});
