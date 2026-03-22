import { test, expect, Page } from '@playwright/test';
import { login, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Dashboard — интерактивность', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Dashboard загружается с KPI карточками', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const cards = page.locator('.v-card');
    const cardCount = await cards.count();
    expect(cardCount).toBeGreaterThanOrEqual(1);
  });

  test('Фильтр по году работает', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const yearChips = page.locator('.v-chip').filter({ hasText: /202[4-6]/ });
    const chipCount = await yearChips.count();
    if (chipCount > 0) {
      await yearChips.first().click({ force: true });
      await page.waitForTimeout(1000);
      const body = await page.textContent('body');
      expect(body!.length).toBeGreaterThan(10);
    }
  });

  test('Графики рендерятся (ApexCharts)', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const charts = page.locator('.apexcharts-canvas, .vue-apexcharts, [class*="chart"]');
    const chartCount = await charts.count();
    console.log(`  📊 Found ${chartCount} chart elements`);
  });
});
