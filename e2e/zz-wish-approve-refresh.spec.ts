import { test, expect, Page } from '@playwright/test';
import { execSync } from 'child_process';
import { dismissOrgPicker, waitForOverlays, collectApiErrors } from './helpers';

// Приёмка: useWishApprovers.ts (decideApprover -> reloadActiveTab),
// WishFormDialog.vue (reloadActiveTab передаётся, живой поллер тоже зовёт её),
// useWishForm.ts::openEditDialog (статус/шапка из свежего GET /wishes/{id}).
// Баг с прода: последний согласующий нажал «Согласовать» из вкладки
// «На согласование мне» — заявка стала converted, но список и повторное
// открытие показывали «На согласовании».
//
// Тестовые заявки созданы в beforeAll SQL-инъекцией (subsidy 61 «ДНР», org 29,
// категория-лист 4848) — одна цепочка из согласующего qa_revision_executor.

const SCREENSHOT_DIR = 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/d36d66f7-79cb-4df8-99d0-d97e5330b8cd/scratchpad/accept/wish-approve-refresh';

function psql(sql: string): string {
  const out = execSync(
    `docker compose -p vsks_crm exec -T db psql -U vsks -d vsks_crm -t -A -c "${sql.replace(/"/g, '\\"')}"`,
    { encoding: 'utf-8' }
  );
  return out.trim();
}

const WISH_1 = Number(process.env.QA_WISH_1 || 2916);
const WISH_2 = Number(process.env.QA_WISH_2 || 2917);

async function loginAs(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.evaluate(() => { try { localStorage.clear(); } catch {} });
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill(username);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 20_000 });
  await page.waitForLoadState('networkidle');
  await waitForOverlays(page);
  await dismissOrgPicker(page);
}

test.describe('Согласование заявки — обновление списка после решения', () => {
  test.setTimeout(300_000);

  test('Сценарий 1: единственный согласующий решает из «На согласование мне»', async ({ page }) => {
    const apiErrors = collectApiErrors(page);
    const requests: string[] = [];
    page.on('request', (r) => {
      if (r.url().includes('/api/wishes')) requests.push(`${r.method()} ${r.url()}`);
    });

    await page.setViewportSize({ width: 1600, height: 1000 });
    await loginAs(page, 'qa_revision_executor', 'QaTest123!');
    await page.goto('/wishes');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1000);

    const incomingTab = page.getByRole('tab', { name: /На согласование мне/i });
    await incomingTab.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const row = page.getByText('QA приёмка: согласование сценарий 1', { exact: false }).first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await row.click();
    await page.waitForTimeout(1200);
    await waitForOverlays(page);

    await page.screenshot({ path: `${SCREENSHOT_DIR}/01-dialog-before-decide.png`, fullPage: true });

    const dialogScope = page.locator('.v-overlay--active .v-card, .v-dialog--active .v-card').first();
    const approveBtn = dialogScope.getByRole('button', { name: /^Согласовать$/i }).last();
    await approveBtn.scrollIntoViewIfNeeded();
    await expect(approveBtn).toBeVisible({ timeout: 10_000 });

    const decideRespPromise = page.waitForResponse(
      r => r.url().includes('/approvers/') && r.url().includes('/decide') && r.request().method() === 'POST',
      { timeout: 30_000 },
    );
    await approveBtn.click({ force: true });
    const decideResp = await decideRespPromise;
    console.log('decide response status (scenario 1):', decideResp.status());
    // Дать Vue дорисовать результат (snackbar/вкладка) после ответа.
    await page.waitForTimeout(800);

    await page.screenshot({ path: `${SCREENSHOT_DIR}/02-dialog-after-decide.png`, fullPage: true });

    const dialogText = await page.locator('.v-overlay--active, .v-dialog--active').first().innerText().catch(() => '');
    console.log('dialog text after decide:', dialogText.slice(0, 500));

    // Закрыть окно — нижняя кнопка «ЗАКРЫТЬ» (верхний mdi-close может быть
    // задизейблен, пока диалог ещё в состоянии loading сразу после decide).
    const closeBtn = page.locator('.v-overlay--active button:has-text("Закрыть")').first();
    await closeBtn.waitFor({ state: 'visible', timeout: 10_000 }).catch(() => {});
    if (await closeBtn.isEnabled({ timeout: 5000 }).catch(() => false)) {
      await closeBtn.click();
    } else {
      await page.keyboard.press('Escape');
    }
    await page.waitForTimeout(1500);
    await waitForOverlays(page);

    await page.screenshot({ path: `${SCREENSHOT_DIR}/03-list-after-close.png`, fullPage: true });

    const rowAfter = page.getByText('QA приёмка: согласование сценарий 1', { exact: false }).first();
    const stillInList = await rowAfter.isVisible({ timeout: 3000 }).catch(() => false);
    if (stillInList) {
      const rowText = await rowAfter.locator('xpath=ancestor::tr[1]').innerText().catch(() => '');
      console.log('row text if still present:', rowText);
      expect(rowText.toLowerCase()).not.toContain('на согласовании');
    }

    const dbStatus = psql(`select status from wishes where id=${WISH_1}`);
    console.log('DB status wish 1 after decide:', dbStatus);
    expect(['approved', 'converted']).toContain(dbStatus);

    const sawListRefresh = requests.some(r => r.includes('assigned_to_me=true') && r.startsWith('GET'));
    console.log('wishes requests:', requests);
    console.log('saw GET assigned_to_me=true after decide:', sawListRefresh);
    expect(sawListRefresh).toBeTruthy();

    console.log('API errors scenario 1:', apiErrors);
    expect(apiErrors.filter(e => !e.includes('/favicon'))).toEqual([]);
  });

  test('Сценарий 2: устаревший список — решение через API, затем клик по старой строке', async ({ page }) => {
    const apiErrors = collectApiErrors(page);
    await page.setViewportSize({ width: 1600, height: 1000 });
    await loginAs(page, 'qa_revision_executor', 'QaTest123!');
    await page.goto('/wishes');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);
    await page.waitForTimeout(1000);

    const incomingTab = page.getByRole('tab', { name: /На согласование мне/i });
    await incomingTab.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    const row = page.getByText('QA приёмка: согласование сценарий 2', { exact: false }).first();
    await expect(row).toBeVisible({ timeout: 15_000 });

    // Решить ЧЕРЕЗ API, не трогая страницу — список в браузере остаётся устаревшим.
    const token = await page.evaluate(() => localStorage.getItem('auth_token'));
    const approvalId = psql(`select id from wish_approvals where wish_id=${WISH_2} and user_id=9550`);
    const decideResp = await page.request.post(`http://localhost:8079/api/wishes/${WISH_2}/approvers/${approvalId}/decide`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { decision: 'approved', comment: null },
    });
    console.log('API decide status:', decideResp.status());
    expect(decideResp.ok()).toBeTruthy();

    // Клик по строке, которая в DOM всё ещё показывает «На согласовании».
    await row.click();
    await page.waitForTimeout(1500);
    await waitForOverlays(page);
    await page.screenshot({ path: `${SCREENSHOT_DIR}/04-stale-row-opened.png`, fullPage: true });

    const dialog = page.locator('.v-overlay--active, .v-dialog--active').first();
    const dialogText = await dialog.innerText().catch(() => '');
    console.log('dialog text after opening stale row:', dialogText.slice(0, 500));
    expect(dialogText.toLowerCase()).not.toContain('на согласовании');

    console.log('API errors scenario 2:', apiErrors);
    expect(apiErrors.filter(e => !e.includes('/favicon'))).toEqual([]);
  });
});
