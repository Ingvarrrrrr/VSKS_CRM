import { test, expect } from '@playwright/test';
// Разовая приёмка 2026-09-29: удаление товара из каталога.
// Жалоба владельца — DELETE /api/products/4280 падал 500 (ForeignKeyViolationError,
// товар стоял в позиции закупки РЕЕ-2026-00921). Проверяем два сценария:
// 1) товар, стоящий в позиции закупки (используем существующий каталожный товар с
//    известными связями, чтобы не собирать заявку/закупку целиком через API) — 409
//    с понятным текстом и ссылкой на закупку;
// 2) свежесозданный неиспользуемый товар — удаляется штатно.

async function login(page: any) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('.v-btn').filter({ hasText: /войти|вход/i }).first().click();
  await page.waitForURL((url: URL) => !url.pathname.includes('/login'), { timeout: 15_000 });
  // Обходим окно «Выберите организации» (память проекта: local_frontend_no_hmr) —
  // без него оверлей перехватывает клики по остальному UI.
  await page.evaluate(() => {
    localStorage.setItem('selected_org_ids', JSON.stringify([1]));
    localStorage.setItem('selected_org_names', JSON.stringify(['ВСКС']));
    localStorage.setItem('active_org_id', '1');
  });
}

test('удаление товара, занятого в закупках/заявках — блокируется с понятной причиной', async ({ page, request, baseURL }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('auth_token'));
  expect(token).toBeTruthy();

  // Находим через API товар, реально стоящий в позициях закупок (тот же
  // класс проблемы, что и боевой инцидент с product_id=4280) — не полагаемся
  // на конкретный id, ищем в каталоге по имени из инцидента, иначе берём
  // первый товар из delete-impact-положительного набора через прямой SQL-подобный
  // эндпоинт недоступен с фронта, поэтому используем известный устойчивый пример.
  const listResp = await request.get(`${baseURL}/api/products/?search=Логистические услуги`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(listResp.ok(), await listResp.text()).toBeTruthy();
  const list = await listResp.json();
  expect(list.length, 'ожидался хотя бы один товар "Логистические услуги" с историческими связями').toBeGreaterThan(0);
  const product = list[0];

  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const search = page.getByRole('textbox', { name: 'Поиск по наименованию / описанию' });
  await search.fill('Логистические услуги');
  await page.waitForTimeout(800);

  await page.locator('.v-btn:has(.mdi-delete-outline)').first().click();
  await page.waitForTimeout(300);
  await page.locator('.v-btn').filter({ hasText: /^Удалить$/i }).first().click();
  await page.waitForTimeout(1200);

  await page.screenshot({ path: 'test-results/product-delete-blocked.png', fullPage: true });

  const alertText = await page.locator('.v-alert').first().innerText();
  console.log('BLOCK_MESSAGE', alertText);
  expect(alertText).toContain('нельзя удалить');

  // Хотя бы одна ссылка на закупку из диалога ведёт на реальный маршрут /orders/{id}.
  const orderLinks = page.locator('a[href^="/orders/"]');
  await expect(orderLinks.first()).toBeVisible();
  const href = await orderLinks.first().getAttribute('href');
  console.log('FIRST_ORDER_LINK', href);
  expect(href).toMatch(/^\/orders\/\d+$/);

  // Товар остаётся в каталоге — диалог не позволил удалить.
  const getResp = await request.get(`${baseURL}/api/products/${product.id}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(getResp.ok()).toBeTruthy();
});

test('удаление неиспользуемого товара — проходит штатно', async ({ page, request, baseURL }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('auth_token'));

  const suffix = Date.now();
  const productResp = await request.post(`${baseURL}/api/products/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: `E2E неиспользуемый товар ${suffix}`, category: 'Прочее' },
  });
  expect(productResp.ok(), await productResp.text()).toBeTruthy();
  const product = await productResp.json();

  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const search = page.getByRole('textbox', { name: 'Поиск по наименованию / описанию' });
  await search.fill(`E2E неиспользуемый товар ${suffix}`);
  await page.waitForTimeout(800);

  await page.locator('.v-btn:has(.mdi-delete-outline)').first().click();
  await page.waitForTimeout(300);
  await page.locator('.v-btn').filter({ hasText: /^Удалить$/i }).first().click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: 'test-results/product-delete-ok.png', fullPage: true });

  const getResp = await request.get(`${baseURL}/api/products/${product.id}`, { headers: { Authorization: `Bearer ${token}` } });
  expect(getResp.status()).toBe(404);
});
