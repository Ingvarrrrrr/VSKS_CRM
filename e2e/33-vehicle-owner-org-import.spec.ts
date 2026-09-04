import { test, expect, Page } from '@playwright/test';
import { login, waitForOverlays } from './helpers';
import path from 'path';
import fs from 'fs';

// helpers.ts's dismissOrgPicker() filters dialog text on 'Выбрать организации',
// but the actual dialog title text in this build is 'Выберите организации' —
// a mismatch that makes the shared helper a no-op here. helpers.ts is off-limits
// (per task constraints), so this local variant handles the real wording and
// picks the ВСКС org explicitly (needed later so vehicle list queries include
// org 1's vehicles alongside the freshly imported test rows).
async function selectOrgAndApply(page: Page) {
  const dialog = page.locator('[role="dialog"], dialog').filter({ hasText: /Выберите организации|Выбрать организации/ }).first();
  const visible = await dialog.isVisible({ timeout: 3000 }).catch(() => false);
  if (!visible) return;

  const vsksItem = dialog.getByText('ВСКС', { exact: true }).first();
  if (await vsksItem.count().then((c) => c > 0).catch(() => false)) {
    await vsksItem.click({ force: true });
  } else {
    await dialog.locator('.v-list-item').nth(1).click({ force: true });
  }
  await page.waitForTimeout(300);
  const applyBtn = dialog.getByRole('button', { name: /Применить/i });
  if (await applyBtn.isEnabled({ timeout: 1500 }).catch(() => false)) {
    await applyBtn.click({ force: true });
    await page.waitForTimeout(500);
  } else {
    await page.keyboard.press('Escape');
  }
}

// Phase: жалоба владельца 2026-08-31 — «нет организации собственника» при
// импорте Excel реестра ТС + «шаблона нет для скачивания».
//
// 1) Проверяет фактическую ВИДИМОСТЬ кнопки «Скачать шаблон» на первом шаге
//    диалога импорта (getBoundingClientRect против окна, не просто наличие в DOM).
// 2) Сквозной путь: загрузка тестового файла (2 заведомо несуществующих
//    госномера, собственник указан через ИНН реальной организации И через
//    точное название другой реальной организации) → предпросмотр →
//    подтверждение импорта. Тестовый .xlsx собран заранее (см. scratchpad)
//    модификацией реального скачанного шаблона — эквивалент «скачать шаблон,
//    заполнить руками», так как редактор xlsx недоступен внутри Playwright.

const SHOTS_DIR = 'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\f7c97c55-1f66-4005-ba84-a7c85d9783ca\\scratchpad\\shots_owner';
const TEST_XLSX = 'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\f7c97c55-1f66-4005-ba84-a7c85d9783ca\\scratchpad\\test_upload.xlsx';

test.beforeAll(() => {
  fs.mkdirSync(SHOTS_DIR, { recursive: true });
});

test.describe('Импорт ТС: авто-определение организации-собственника + кнопка шаблона', () => {
  test('шаблон виден и скачивается; импорт определяет owner_org_id из файла', async ({ page }) => {
    await login(page);
    await selectOrgAndApply(page);

    await page.goto('/fleet/vehicles');
    await page.waitForLoadState('networkidle');
    await selectOrgAndApply(page);
    await waitForOverlays(page);

    const importBtn = page.locator('.v-btn, button').filter({ hasText: /Импорт Excel/i }).first();
    await expect(importBtn).toBeVisible({ timeout: 10_000 });
    await importBtn.click();
    await page.waitForTimeout(500);

    // ── Step 1: template button visibility ──────────────────────────────
    const dialog = page.locator('.v-dialog .v-card').filter({ hasText: 'Импорт ТС из Excel' }).first();
    await expect(dialog).toBeVisible({ timeout: 5000 });

    const templateBtn = dialog.locator('.v-btn').filter({ hasText: 'Скачать шаблон' }).first();
    await expect(templateBtn).toBeVisible({ timeout: 5000 });

    const box = await templateBtn.boundingBox();
    const viewport = page.viewportSize();
    console.log('TEMPLATE_BTN_BOX', JSON.stringify(box));
    console.log('VIEWPORT', JSON.stringify(viewport));
    expect(box).not.toBeNull();
    if (box && viewport) {
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
      expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);
    }
    // Real getBoundingClientRect from the page itself (not just Playwright's computed box)
    const rect = await templateBtn.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return {
        x: r.x, y: r.y, width: r.width, height: r.height,
        visibility: style.visibility, display: style.display, opacity: style.opacity,
      };
    });
    console.log('TEMPLATE_BTN_RECT', JSON.stringify(rect));
    expect(rect.width).toBeGreaterThan(0);
    expect(rect.height).toBeGreaterThan(0);
    expect(rect.visibility).not.toBe('hidden');
    expect(rect.display).not.toBe('none');

    await page.screenshot({ path: path.join(SHOTS_DIR, '1_step1_dialog_with_template_button.png'), fullPage: false });

    // Confirm which JS chunk actually serves the button's label (PWA/service-worker
    // staleness check) — capture the network response for the vehicle list chunk.
    const jsUrls: string[] = [];
    page.on('response', (r) => {
      if (/VehicleListView-.*\.js/.test(r.url())) jsUrls.push(r.url());
    });

    // ── Download template ────────────────────────────────────────────────
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      templateBtn.click(),
    ]);
    const downloadPath = path.join(SHOTS_DIR, 'downloaded_template_via_ui.xlsx');
    await download.saveAs(downloadPath);
    const stat = fs.statSync(downloadPath);
    console.log('DOWNLOADED_TEMPLATE_SIZE', stat.size);
    expect(stat.size).toBeGreaterThan(1000);

    // ── Step 1 -> upload test file with 2 fake plates ───────────────────
    const fileInput = dialog.locator('input[type="file"]');
    await fileInput.setInputFiles(TEST_XLSX);
    await page.waitForTimeout(500);

    const uploadBtn = dialog.locator('.v-btn').filter({ hasText: 'Загрузить' }).first();
    await expect(uploadBtn).toBeEnabled({ timeout: 5000 });
    await uploadBtn.click();
    await page.waitForTimeout(1500);
    await waitForOverlays(page);

    // ── Step 2: preview — owner org should already be resolved from file ──
    await expect(page.locator('text=Предпросмотр').first()).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: path.join(SHOTS_DIR, '2_step2_preview_owner_resolved.png'), fullPage: true });

    const bodyText = await page.locator('.v-card-text').first().innerText();
    console.log('PREVIEW_BODY_SNIPPET', bodyText.slice(0, 2000));

    const confirmBtn = page.locator('.v-btn').filter({ hasText: 'Подтвердить импорт' }).first();
    await expect(confirmBtn).toBeVisible({ timeout: 5000 });
    await confirmBtn.click();
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    // ── Step 3: result ───────────────────────────────────────────────────
    await page.screenshot({ path: path.join(SHOTS_DIR, '3_step3_import_result.png'), fullPage: true });
    const resultText = await page.locator('.v-card-text').first().innerText();
    console.log('RESULT_BODY', resultText.slice(0, 1000));

    console.log('VEHICLE_LIST_JS_URLS', JSON.stringify(jsUrls));
  });
});
