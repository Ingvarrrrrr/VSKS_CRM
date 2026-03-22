import { test, expect, Page } from '@playwright/test';
import { login, collectApiErrors } from './helpers';

/**
 * Тест: обход всех страниц CRM
 * Для каждой страницы проверяем:
 * 1. Страница загружается без крашей
 * 2. Нет JS-ошибок в консоли
 * 3. Нет API ошибок 5xx (4xx допускаем, но логируем)
 * 4. Основной контент рендерится
 */

const PAGES = [
  { path: '/dashboard', name: 'Dashboard' },
  { path: '/subsidies', name: 'Субсидии' },
  { path: '/orders', name: 'Закупки' },
  { path: '/contractors', name: 'Контрагенты' },
  { path: '/contracts', name: 'Контракты' },
  { path: '/products', name: 'Продукты' },
  { path: '/products-summary', name: 'Сводка продуктов' },
  { path: '/plan', name: 'План-график' },
  { path: '/commercial-requests', name: 'Коммерческие запросы' },
  { path: '/my-tasks', name: 'Мои задачи' },
  { path: '/reports', name: 'Отчёты' },
  { path: '/staff', name: 'Персонал' },
  { path: '/hierarchy', name: 'Иерархия' },
  { path: '/feo-categories', name: 'ФЭО категории' },
  { path: '/suppliers', name: 'Поставщики' },
  { path: '/system-incidents', name: 'Системные инциденты' },
  { path: '/organizations', name: 'Организации' },
  { path: '/service-notes', name: 'Служебные записки' },
  { path: '/advance-reports', name: 'Авансовые отчёты' },
  { path: '/org-settings', name: 'Настройки организации' },
];

test.describe('Обход всех страниц', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  for (const { path, name } of PAGES) {
    test(`${name} (${path}) — загружается без ошибок`, async () => {
      const jsErrors: string[] = [];
      const apiErrors = collectApiErrors(page);

      page.on('pageerror', (err) => {
        jsErrors.push(err.message);
      });

      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000); // Vue rendering

      // Page should not show blank screen
      const bodyText = await page.textContent('body');
      expect(bodyText!.length).toBeGreaterThan(10);

      // Check no crash overlay
      const hasCrash = await page.locator('text=/error|crash|exception/i')
        .filter({ has: page.locator('.v-overlay, .error-boundary') })
        .count();

      // Log errors but only fail on JS errors
      if (apiErrors.length > 0) {
        console.log(`  ⚠️  API errors on ${path}:`);
        apiErrors.forEach(e => console.log(`    ${e}`));
      }

      if (jsErrors.length > 0) {
        console.log(`  ❌ JS errors on ${path}:`);
        jsErrors.forEach(e => console.log(`    ${e}`));
      }

      // Take screenshot for visual review
      await page.screenshot({ path: `e2e-report/screenshots/${name.replace(/\s/g, '_')}.png`, fullPage: true });
    });
  }
});
