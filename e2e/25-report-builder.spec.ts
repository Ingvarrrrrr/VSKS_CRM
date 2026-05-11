import { test, expect } from '@playwright/test';
import { login, dismissOrgPicker } from './helpers';

const BASE_URL = process.env.BASE_URL || 'http://85.239.53.155';

/**
 * Phase 25 — Report Builder smoke tests (10 tests: API + UI)
 * Covers: region field, analytics/fields, analytics/query (list+pivot),
 *         report-configs, ListBuilder UI, PivotBuilder UI, DashboardBuilder UI,
 *         Excel export, PDF export.
 *
 * NOTE: loginAs helper does not exist in this codebase — using login(page) instead
 * (hardcoded admin/admin123 in helpers.ts). For API tests we use REST login directly.
 */

test.describe('Phase 25 — Report Builder smoke', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await dismissOrgPicker(page);
  });

  // ------------------------------------------------------------------ UI TESTS

  test('25-01 Регион виден в карточке закупки', async ({ page }) => {
    await page.goto(`${BASE_URL}/orders`);
    await page.waitForLoadState('networkidle');
    // Открыть первую закупку (если есть строки)
    const firstRow = page.locator('tbody tr').first();
    if (await firstRow.isVisible({ timeout: 5000 })) {
      await firstRow.click();
      await page.waitForURL(/\/orders\/\d+\/edit/);
      // Поле «Регион проведения мероприятия» — autocomplete с RUSSIAN_REGIONS
      const regionField = page.getByLabel('Регион проведения мероприятия');
      await expect(regionField).toBeVisible({ timeout: 10000 });
    }
  });

  test('25-05 ListBuilder открывается и каталог полей грузится', async ({ page }) => {
    await page.goto(`${BASE_URL}/reports/lists/new`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Новый реестр').first()).toBeVisible({ timeout: 10000 });
    // Каталог полей слева — accordion groups
    const expansion = page.locator('.v-expansion-panel-title').first();
    await expect(expansion).toBeVisible({ timeout: 8000 });
  });

  test('25-06 PivotBuilder открывается', async ({ page }) => {
    await page.goto(`${BASE_URL}/reports/pivots/new`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Новая сводная').first()).toBeVisible({ timeout: 10000 });
    // Drop-зоны
    await expect(page.getByText('Строки').first()).toBeVisible();
    await expect(page.getByText('Колонки').first()).toBeVisible();
    await expect(page.getByText('Значения (меры)')).toBeVisible();
  });

  test('25-07 DashboardBuilder открывается', async ({ page }) => {
    await page.goto(`${BASE_URL}/dashboards/new`);
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Новый дашборд').first()).toBeVisible({ timeout: 10000 });
    // Кнопка «Виджет» в режиме редактирования
    await expect(page.getByRole('button', { name: /Виджет/i })).toBeVisible();
  });

  // ----------------------------------------------------------------- API TESTS

  test('25-02 GET /api/analytics/fields отдаёт >= 60 полей', async ({ request }) => {
    const loginResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    });
    expect(loginResp.ok()).toBeTruthy();
    const { access_token } = await loginResp.json();

    const resp = await request.get(`${BASE_URL}/api/analytics/fields`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.fields.length).toBeGreaterThanOrEqual(60);
    expect(data.groups.length).toBeGreaterThan(3);
    // region должен быть в списке (Plan 25-01)
    expect(data.fields.find((f: any) => f.key === 'region')).toBeTruthy();
  });

  test('25-03 POST /api/analytics/query возвращает rows (list)', async ({ request }) => {
    const loginResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    });
    const { access_token } = await loginResp.json();

    const resp = await request.post(`${BASE_URL}/api/analytics/query`, {
      headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
      data: {
        kind: 'list',
        columns: ['purchase_number', 'item_name', 'planned_total_price'],
        filters: {},
        limit: 5,
      },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data.rows)).toBeTruthy();
    expect(data.kind).toBe('list');
  });

  test('25-03b POST /api/analytics/query pivot возвращает totals', async ({ request }) => {
    const loginResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    });
    const { access_token } = await loginResp.json();

    const resp = await request.post(`${BASE_URL}/api/analytics/query`, {
      headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
      data: {
        kind: 'pivot',
        rows: ['item_type'],
        cols: [],
        measures: [{ field: 'planned_total_price', agg: 'sum' }],
        filters: {},
      },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(data.kind).toBe('pivot');
    expect(typeof data.totals).toBe('object');
  });

  test('25-04 GET /api/report-configs не падает', async ({ request }) => {
    const loginResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    });
    const { access_token } = await loginResp.json();

    const resp = await request.get(`${BASE_URL}/api/report-configs/?kind=list`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(resp.ok()).toBeTruthy();
    const data = await resp.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('25-08 Excel-экспорт возвращает .xlsx (binary)', async ({ request }) => {
    const loginResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    });
    const { access_token } = await loginResp.json();

    const resp = await request.post(`${BASE_URL}/api/analytics/export.xlsx`, {
      headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
      data: {
        config: {
          kind: 'list',
          columns: ['purchase_number', 'item_name'],
          filters: {},
          limit: 10,
        },
        name: 'E2E_test_list',
      },
    });
    expect(resp.ok()).toBeTruthy();
    const buf = await resp.body();
    expect(buf.length).toBeGreaterThan(5000); // > 5KB
    expect(resp.headers()['content-type']).toContain('spreadsheet');
  });

  test('25-09 PDF-экспорт возвращает .pdf (PDF header)', async ({ request }) => {
    const loginResp = await request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'admin', password: 'admin123' },
    });
    const { access_token } = await loginResp.json();

    const resp = await request.post(`${BASE_URL}/api/analytics/export.pdf`, {
      headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' },
      data: {
        config: {
          kind: 'list',
          columns: ['purchase_number', 'item_name'],
          filters: {},
          limit: 5,
        },
        name: 'E2E_test_pdf',
      },
    });
    expect(resp.ok()).toBeTruthy();
    const buf = await resp.body();
    // PDF magic bytes — первые 4 байта = "%PDF"
    expect(buf.slice(0, 4).toString()).toBe('%PDF');
    expect(buf.length).toBeGreaterThan(500);
  });
});
