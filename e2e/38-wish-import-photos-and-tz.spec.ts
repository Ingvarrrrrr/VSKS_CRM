import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import { login } from './helpers';

/**
 * Владелец (2026-09-16), два требования:
 *  1) Импорт xlsx-листа В ЗАЯВКУ подтягивает картинки для позиций, уже
 *     существующих в каталоге (import-smart-nopid теперь делает точное
 *     сопоставление по имени — см. purchase_items_import_smart.py).
 *  2) Секция «Техническое задание» у заявки — свёрнутая копия секции закупки
 *     (WishTzSection.vue), со скачиванием .docx (wish_documents.py,
 *     GET /{wish_id}/documents/tech_spec).
 *
 * Тестовый xlsx строится openpyxl-эквивалентом (exceljs недоступен в
 * node_modules этого проекта, файл собирается вручную минимальным XLSX
 * writer через exceljs, если есть; иначе — через python3 openpyxl в
 * контейнере backend, копируется на хост). Здесь используем python3 внутри
 * backend-контейнера — гарантированно доступен (сам продукт на Python).
 *
 * Тестовая заявка удаляется в конце (через DELETE /api/wishes/{id} с тем же
 * токеном, что использует UI) — требование задания «тестовую заявку удалить».
 */

const SCREEN_DIR = 'C:\\Users\\1\\Documents\\VAULT_for_LLM\\Projects\\VSKS_CRM\\Artifacts';
const XLSX_HOST_PATH = path.join(
  'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\5ec4f423-8de0-4040-b204-1a9a8f888e77\\scratchpad',
  'wish_import_test.xlsx'
);

// Товары, реально существующие в локальном каталоге (см. таблицу products на
// стенде) — один с photo_url, один с фото в bytea (photo_data), чтобы
// проверить оба пути effective_photo_url(); плюс одно название НЕ из
// каталога — контроль, что для него фото не появляется и каталог не растёт.
const CATALOG_NAME_1 = 'Переносной генератор огнетушащего аэрозоля ГОА ТОР-2800 (ОП)';
const CATALOG_NAME_2 = 'Автошина Yokohama 215/75 R16C 116/114R BluEarth-Van RY55';
const NOT_IN_CATALOG_NAME = 'E2E-НеВКаталоге-20260916-Тестовый товар';

test.beforeAll(() => {
  // Строим xlsx через python3+openpyxl в backend-контейнере (тот же образ,
  // что гоняет pytest) и копируем на хост, чтобы Playwright мог его загрузить.
  const py = `
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.append(["Наименование", "Количество", "Цена за ед.", "Ед. изм."])
ws.append(["${CATALOG_NAME_1}", 1, 25000, "шт"])
ws.append(["${CATALOG_NAME_2}", 4, 8000, "шт"])
ws.append(["${NOT_IN_CATALOG_NAME}", 1, 1000, "шт"])
wb.save("/tmp/wish_import_test.xlsx")
`;
  fs.writeFileSync(path.join(path.dirname(XLSX_HOST_PATH), '_build_xlsx.py'), py, 'utf-8');
  execSync(
    `docker cp "${path.join(path.dirname(XLSX_HOST_PATH), '_build_xlsx.py')}" vsks_crm-backend_a-1:/tmp/_build_xlsx.py`
  );
  execSync(`docker exec vsks_crm-backend_a-1 python3 /tmp/_build_xlsx.py`);
  execSync(`docker cp vsks_crm-backend_a-1:/tmp/wish_import_test.xlsx "${XLSX_HOST_PATH}"`);
  expect(fs.existsSync(XLSX_HOST_PATH)).toBe(true);
});

test('импорт xlsx в заявку подтягивает фото из каталога; ТЗ сворачивается и скачивается', async ({ page }) => {
  await login(page);
  await page.goto('/wishes');
  await page.waitForLoadState('networkidle');

  // ── Открыть создание заявки ──────────────────────────────────────────────
  await page.locator('button:has(.mdi-plus)').last().click();
  await expect(page.getByText('Новая заявка', { exact: false }).first()).toBeVisible({ timeout: 10_000 });

  const title = `E2E ТЗ и фото 20260916 ${Date.now()}`;
  await page.locator('[data-field="title"] input').fill(title);

  // ── Импорт из файла (умный режим — дефолт) ───────────────────────────────
  await page.getByRole('button', { name: 'Импорт из файла' }).click();
  await expect(page.getByText('Умный импорт позиций')).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles(XLSX_HOST_PATH);
  await page.getByRole('button', { name: 'Распознать' }).click();
  await expect(page.getByText('Распознано позиций:')).toBeVisible({ timeout: 15_000 });

  await page.getByRole('button', { name: 'Добавить позиции' }).click();

  // Диалог сопоставления с каталогом (POST /products/match запускается
  // фронтом для ВСЕХ строк независимо от backend'ного точного матча — но
  // exact-match из backend главнее при коммите, см. useItemsImport.ts).
  // Один из трёх товаров заведомо не из каталога → диалог гарантированно
  // появляется (create-branch), ждём его явно, а не проверяем isVisible()
  // без ожидания (та проверка гонится с задержкой сетевого /products/match).
  await expect(page.getByText('Сопоставление товаров с каталогом')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: /Применить сопоставление/ }).click();

  // ── Проверка: фото появились у позиций из каталога ───────────────────────
  // (ТЗ-секция ниже тоже рендерит те же фото, но свёрнута v-show — не видна;
  // считаем только ВИДИМЫЕ <img>, чтобы не задваивать по скрытой таблице ТЗ.)
  await expect(page.locator('img:visible')).toHaveCount(2, { timeout: 10_000 });
  // Дать диалогам домой закрыться/анимации осесть перед скриншотом.
  await expect(page.getByText('Сопоставление товаров с каталогом')).toBeHidden({ timeout: 10_000 });
  await page.locator('.v-snackbar__wrapper').first().waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(800);

  await page.screenshot({ path: path.join(SCREEN_DIR, 'wish_import_photos.png'), fullPage: true });

  // ── Сохранить черновик (нужен id заявки для скачивания ТЗ) ───────────────
  const savePromise = page.waitForResponse(r => r.url().includes('/api/wishes/') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Сохранить черновик' }).click();
  const saveResp = await savePromise;
  const created = await saveResp.json();
  const wishId: number = created.id;
  expect(wishId).toBeGreaterThan(0);

  // ── Секция ТЗ: свёрнута по умолчанию, раскрывается по клику ──────────────
  const tzHeader = page.getByText('Техническое задание', { exact: true });
  await expect(tzHeader).toBeVisible();
  const tzBodyBefore = page.locator('.wish-tz-table');
  await expect(tzBodyBefore).toBeHidden();

  await tzHeader.click();
  await expect(page.locator('.wish-tz-table')).toBeVisible();
  await expect(page.locator('.wish-tz-table')).toContainText(CATALOG_NAME_1);
  await expect(page.locator('.wish-tz-table')).toContainText(NOT_IN_CATALOG_NAME);

  await page.screenshot({ path: path.join(SCREEN_DIR, 'wish_tz.png'), fullPage: true });

  // ── Скачать ТЗ (.docx) ────────────────────────────────────────────────────
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /Скачать ТЗ/ }).click();
  const download = await downloadPromise;
  const suggested = download.suggestedFilename();
  expect(suggested.endsWith('.docx')).toBe(true);
  const savedPath = path.join(path.dirname(XLSX_HOST_PATH), suggested);
  await download.saveAs(savedPath);
  const stat = fs.statSync(savedPath);
  expect(stat.size).toBeGreaterThan(1000);

  // ── Удалить тестовую заявку ───────────────────────────────────────────────
  const token = await page.evaluate(() => localStorage.getItem('auth_token'));
  const delResp = await page.request.delete(`http://localhost:8079/api/wishes/${wishId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect([200, 204]).toContain(delResp.status());

  const check = execSync(
    `docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm -t -A -c "select count(*) from wishes where id=${wishId};"`,
    { encoding: 'utf-8' }
  ).trim();
  expect(check).toBe('0');

  // Каталог не пополнился несматченным товаром (владелец, 2026-09-04).
  const catalogCheck = execSync(
    `docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm -t -A -c "select count(*) from products where name='${NOT_IN_CATALOG_NAME}';"`,
    { encoding: 'utf-8' }
  ).trim();
  expect(catalogCheck).toBe('0');
});
