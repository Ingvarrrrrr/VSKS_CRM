import { test, expect } from '@playwright/test';
import path from 'path';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3002';
const SCREENSHOT_DIR = path.resolve(__dirname, '../.tmp_test');

test.use({
  viewport: { width: 390, height: 844 },
  baseURL: BASE_URL,
});

async function login(page: any) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
}

async function collectMetrics(page: any) {
  return page.evaluate(() => {
    const bar = document.querySelector('.v-app-bar');
    const content = document.querySelector('.v-app-bar .v-toolbar__content');
    const navIcon = document.querySelector('.v-app-bar .v-app-bar-nav-icon');
    const main = document.querySelector('.v-main') as HTMLElement | null;

    const r = (el: Element | null) => {
      if (!el) return null;
      const { top, height, left, width } = el.getBoundingClientRect();
      return { top: Math.round(top * 100) / 100, height: Math.round(height * 100) / 100, left, width };
    };

    return {
      bar: r(bar),
      content: r(content),
      navIcon: r(navIcon),
      mainPaddingTop: main ? getComputedStyle(main).paddingTop : null,
    };
  });
}

test('safearea: инсет 0px (базовый)', async ({ page }) => {
  await login(page);
  await page.waitForTimeout(800);

  const metrics = await collectMetrics(page);
  console.log('METRICS_0px:', JSON.stringify(metrics, null, 2));

  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'safearea_0.png'), fullPage: false });
});

test('safearea: эмуляция нотча 47px через --gala-safe-top', async ({ page }) => {
  await login(page);
  await page.waitForTimeout(800);

  // Подставляем 47px вместо env(safe-area-inset-top)
  await page.evaluate(() => {
    document.documentElement.style.setProperty('--gala-safe-top', '47px');
  });

  // Даём браузеру пересчитать layout
  await page.waitForTimeout(400);

  const metrics = await collectMetrics(page);
  console.log('METRICS_47px:', JSON.stringify(metrics, null, 2));

  await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'safearea_47.png'), fullPage: false });

  // --- expect'ы ---
  const bar = metrics.bar!;
  const content = metrics.content!;
  const navIcon = metrics.navIcon!;
  const mainPT = parseFloat(metrics.mainPaddingTop ?? '0');

  // Шапка начинается с самого верха viewport
  expect(bar.top, `bar.top должен быть 0, получили ${bar.top}`).toBe(0);

  // Шапка высотой 48 + 47 = 95px
  expect(bar.height, `bar.height должен быть 95, получили ${bar.height}`).toBe(95);

  // Содержимое шапки НЕ заходит в зону статус-бара
  expect(content.top, `content.top должен быть >= 47, получили ${content.top}`).toBeGreaterThanOrEqual(47);
  expect(content.height, `content.height должен быть 48, получили ${content.height}`).toBe(48);

  // Гамбургер НЕ в зоне часов
  expect(navIcon.top, `navIcon.top должен быть >= 47, получили ${navIcon.top}`).toBeGreaterThanOrEqual(47);

  // Основной контент не прячется под шапкой
  expect(mainPT, `mainPaddingTop должен быть >= 95, получили ${mainPT}`).toBeGreaterThanOrEqual(95);
});
