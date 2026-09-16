import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';

// Владелец (2026-09-16): «Я согласующий заявку — не могу одной кнопкой создать
// всем позициям в заявке плановую позицию» — согласующий по иерархии
// (менеджер+, не в явной цепочке wish_approvals) должен видеть и использовать
// кнопку «Создать в плане закупок» на отправленной заявке (PurchaseItemsEditor
// gate: !readonly || feoAttrsEditable, а feoAttrsEditable = canEditWishFeo,
// см. useWishForm.ts::canDecideWish).
//
// Логин — не формой (пароль пользователя 565 неизвестен), а прямой injection
// JWT в localStorage (auth_token), как заведено для сессий без известных
// паролей — токен получен `create_access_token({'sub': '565', 'org_id': 1})`
// внутри backend-контейнера.
//
// Заявка №21 «Приобретение правовой системы Гарант» (org_id=1, subsidy_id=7,
// created_by=7, submitted, БЕЗ участников цепочки wish_approvals) — заведомо
// НЕ пускала пользователя 565 (manager, org_id=1, не автор/не assigned_to/не
// в цепочке) до фикса canEditWishFeo. Единственная позиция заявки не привязана
// к плановой (feo_planned_item_id IS NULL), категория ФЭО задана на шапке
// (wish.feo_category_id=125, feo_per_item=false) — needPlanRows.

const TOKEN = process.env.WISH_MANAGER_TOKEN || '';

function psql(sql: string): string {
  const out = execSync(
    `docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm -t -A -c "${sql.replace(/"/g, '\\"')}"`,
    { encoding: 'utf-8' }
  );
  return out.trim();
}

test('менеджер вне цепочки видит и использует кнопку массового создания плановых позиций на отправленной заявке', async ({ page }) => {
  expect(TOKEN, 'WISH_MANAGER_TOKEN env var must be set').not.toBe('');

  // Снимок «до»: позиция заявки 21 без плановой привязки.
  const before = psql("select feo_planned_item_id from wish_items where wish_id=21 order by id limit 1");
  expect(before).toBe('');

  await page.goto('/login');
  await page.evaluate((token) => {
    localStorage.setItem('auth_token', token);
  }, TOKEN);
  await page.goto('/wishes');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Заявка №21 не «моя» (менеджер 565 — не автор/не assigned_to) — открыть
  // общую вкладку менеджера «Заявки сотрудников».
  await page.getByRole('tab', { name: /Заявки сотрудников/i }).click();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Список «Заявки сотрудников» большой (50+ отправленных, с пагинацией) —
  // отфильтровать per-column меню колонки «Заявка» (Excel-like
  // ColumnHeaderMenu, см. feedback_column_filter_compromise) вместо прокрутки
  // по страницам.
  await page.locator('th', { hasText: 'Заявка' }).locator('button, i, [role="button"]').first().click();
  await page.waitForTimeout(400);
  const filterInput = page.locator('.v-overlay-container input[type="text"]').first();
  await filterInput.fill('Гарант');
  await page.waitForTimeout(600);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(600);

  const targetRow = page.getByText('Приобретение правовой системы Гарант', { exact: false }).first();
  await targetRow.scrollIntoViewIfNeeded({ timeout: 15_000 });
  await targetRow.click();
  await page.waitForTimeout(1500);

  // Кнопка «Создать в плане закупок» — видна согласующему вне цепочки
  // (регрессия до фикса: кнопка отсутствовала, т.к. canEditWishFeo не считал
  // manager-не-в-цепочке решающим).
  const bulkBtn = page.getByRole('button', { name: /Создать в плане закупок/i }).first();
  await expect(bulkBtn).toBeVisible({ timeout: 10_000 });

  await page.screenshot({
    path: 'C:\\Users\\1\\Documents\\VAULT_for_LLM\\Projects\\VSKS_CRM\\Artifacts\\wish_approver_bulk_plan.png',
    fullPage: true,
  });

  await bulkBtn.click();
  await page.waitForTimeout(500);

  // Диалог подтверждения массового создания — подтвердить.
  const confirmBtn = page.getByRole('button', { name: /^Создать$|Создать позиции|Создать плановые/i }).last();
  await expect(confirmBtn).toBeVisible({ timeout: 5000 });
  await confirmBtn.click();
  await page.waitForTimeout(2000);

  // Проверка по БД, а не только по UI (Lessons: verify_by_content_not_counts).
  const after = psql("select feo_planned_item_id from wish_items where wish_id=21 order by id limit 1");
  expect(after).not.toBe('');
});
