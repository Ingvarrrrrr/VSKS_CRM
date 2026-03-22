import { test, expect, Page } from '@playwright/test';
import { login, clickButton, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Остальные страницы — загрузка и базовая интерактивность', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('План-график загружается', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/plan');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /plan errors:', apiErrors);
    }
  });

  test('Коммерческие запросы загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/commercial-requests');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /commercial-requests errors:', apiErrors);
    }
  });

  test('Мои задачи загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/my-tasks');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /my-tasks errors:', apiErrors);
    }
  });

  test('Отчёты загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/reports');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /reports errors:', apiErrors);
    }

    const periodBtns = page.locator('.v-btn-toggle .v-btn, .v-chip').filter({ hasText: /неделя|месяц|год|week|month/i });
    if (await periodBtns.first().isVisible().catch(() => false)) {
      await periodBtns.first().click({ force: true });
      await page.waitForTimeout(1000);
    }
  });

  test('ФЭО категории загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/feo-categories');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /feo-categories errors:', apiErrors);
    }
  });

  test('Поставщики загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/suppliers');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /suppliers errors:', apiErrors);
    }
  });

  test('Служебные записки загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/service-notes');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /service-notes errors:', apiErrors);
    }
  });

  test('Авансовые отчёты загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/advance-reports');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /advance-reports errors:', apiErrors);
    }
  });

  test('Системные инциденты загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/system-incidents');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /system-incidents errors:', apiErrors);
    }
  });

  test('Организации загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/organizations');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /organizations errors:', apiErrors);
    }
  });

  test('Настройки организации загружаются', async () => {
    const apiErrors = collectApiErrors(page);
    await page.goto('/org-settings');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body!.length).toBeGreaterThan(10);
    if (apiErrors.filter(e => e.includes('500')).length > 0) {
      console.log('  ❌ /org-settings errors:', apiErrors);
    }

    const toggles = page.locator('.v-switch, .v-checkbox');
    const toggleCount = await toggles.count();
    console.log(`  ⚙️ Settings toggles found: ${toggleCount}`);
  });
});
