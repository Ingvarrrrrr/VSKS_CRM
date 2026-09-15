import { test, expect } from '@playwright/test';
import { login, waitForOverlays } from './helpers';

/**
 * Владелец (2026-09-16, дословно): «Удаление и добавление субсидий должно
 * происходить без перезагрузки экрана и без его моргания». До фикса:
 * - onSubsidyDeleted() в SubsidiesView.vue звал `await loadAll()` — полный
 *   перезапрос /dashboard/charts с loading=true, размонтировавший всю сетку;
 * - updateSubsidy() в SubsidyEditDialog.vue звал `await ctx.loadAll()` с тем
 *   же эффектом.
 * После фикса обе операции обновляют allSubsidies локально/точечно и зовут
 * тихий silentRefreshSubsidies() (без loading, без замены массива целиком).
 *
 * Проверяем на dev-сервере (vite, порт 5178 — см. BASE_URL) три вещи разом:
 * 1) полноэкранный индикатор `[data-testid="subsidies-loading"]` НИ РАЗУ не
 *    появляется за всё время сценария (MutationObserver, не поллинг —
 *    ловит и мгновенное появление/исчезание между двумя проверками);
 * 2) соседняя карточка — ТОТ ЖЕ DOM-узел до/после каждой операции (метим
 *    произвольным JS-свойством элемента, а не атрибутом — свойство переживёт
 *    патч пропсов, но не переживёт unmount+remount);
 * 3) видимый сценарий владельца целиком: создать → карточка появилась без
 *    reload → переименовать → обновилось без reload → удалить → исчезла без
 *    reload, тестовая субсидия не остаётся в БД.
 */

const SCREEN_DIR = 'C:\\Users\\1\\Documents\\VAULT_for_LLM\\Projects\\VSKS_CRM\\Artifacts';

test('subsidy add/edit/delete — no full reload, no flicker, same DOM node for neighbor card', async ({ page }) => {
  test.setTimeout(120_000);

  await login(page);
  await page.goto('/subsidies');
  await page.waitForLoadState('networkidle');
  await waitForOverlays(page);

  // Форсируем режим "карточки" (тот же переключатель, что в SubsidyListHeader.vue) —
  // требование владельца сформулировано именно про карточки.
  const cardsBtn = page.locator('.v-btn').filter({ has: page.locator('.mdi-view-grid') }).first();
  if (await cardsBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await cardsBtn.click();
    await page.waitForTimeout(300);
  }

  // MutationObserver, а не поллинг — не пропустит появление/исчезание
  // индикатора между двумя проверками в тесте.
  await page.evaluate(() => {
    (window as any).__loadingSeen = false;
    const obs = new MutationObserver(() => {
      if (document.querySelector('[data-testid="subsidies-loading"]')) {
        (window as any).__loadingSeen = true;
      }
    });
    obs.observe(document.body, { childList: true, subtree: true, attributes: true });
    (window as any).__loadingObserver = obs;
  });
  async function resetLoadingWatch() {
    await page.evaluate(() => { (window as any).__loadingSeen = false; });
  }
  async function assertNoLoadingFlicker(label: string) {
    const seen = await page.evaluate(() => (window as any).__loadingSeen);
    expect(seen, `полноэкранный индикатор загрузки появился во время: ${label}`).toBe(false);
  }

  // Пометить соседнюю (любую существующую) карточку своим JS-свойством, чтобы
  // после add/edit/delete проверить — это тот же самый DOM-элемент, а не
  // пересозданный.
  const existingCards = page.locator('.subsidy-card');
  const neighborCountBefore = await existingCards.count();
  let hasNeighbor = neighborCountBefore > 0;
  if (hasNeighbor) {
    await existingCards.first().evaluate((el, mark) => { (el as any).__e2eMark = mark; }, 'neighbor-mark-v1');
  }
  async function assertNeighborSameNode(label: string) {
    if (!hasNeighbor) return;
    const stillMarked = await page.locator('.subsidy-card').first().evaluate(el => (el as any).__e2eMark === 'neighbor-mark-v1');
    expect(stillMarked, `соседняя карточка была пересоздана (DOM-узел не тот же) во время: ${label}`).toBe(true);
  }

  await page.screenshot({ path: `${SCREEN_DIR}\\subsidy_noflicker_00_before.png`, fullPage: true });

  // ── 1) Создание ──────────────────────────────────────────────────────
  const testName = `TEST_NOFLICKER_${Date.now()}`;
  await resetLoadingWatch();
  await page.getByRole('button', { name: /добавить/i }).first().click();
  const addDialog = page.locator('.v-overlay-container').filter({ hasText: 'Добавить субсидию' }).first();
  await expect(addDialog).toBeVisible();
  await addDialog.locator('input').first().fill(testName); // Название
  // Год уже стоит текущим по умолчанию (new Date().getFullYear()) — не трогаем.
  await addDialog.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(addDialog).toBeHidden({ timeout: 10_000 });

  const newCard = page.locator('.subsidy-card').filter({ hasText: testName });
  await expect(newCard, 'карточка новой субсидии не появилась без reload').toBeVisible({ timeout: 10_000 });
  await assertNoLoadingFlicker('создание субсидии');
  await assertNeighborSameNode('создание субсидии');
  await page.screenshot({ path: `${SCREEN_DIR}\\subsidy_noflicker_01_created.png`, fullPage: true });

  // ── 2) Переименование ────────────────────────────────────────────────
  const renamedName = `${testName}_RENAMED`;
  await resetLoadingWatch();
  await newCard.hover();
  await newCard.locator('button').filter({ has: page.locator('.mdi-pencil') }).click();
  const editDialog = page.locator('.v-overlay-container').filter({ hasText: 'Редактировать субсидию' }).first();
  await expect(editDialog).toBeVisible();
  const nameField = editDialog.locator('input').first();
  await nameField.fill(renamedName);
  await editDialog.getByRole('button', { name: /сохранить/i }).click();
  await expect(editDialog).toBeHidden({ timeout: 10_000 });

  const renamedCard = page.locator('.subsidy-card').filter({ hasText: renamedName });
  await expect(renamedCard, 'карточка не обновилась (переименование) без reload').toBeVisible({ timeout: 10_000 });
  await assertNoLoadingFlicker('переименование субсидии');
  await assertNeighborSameNode('переименование субсидии');
  await page.screenshot({ path: `${SCREEN_DIR}\\subsidy_noflicker_02_renamed.png`, fullPage: true });

  // ── 3) Удаление (это же — уборка за собой тестовых данных) ─────────────
  await resetLoadingWatch();
  await renamedCard.hover();
  await renamedCard.locator('button').filter({ has: page.locator('.mdi-delete') }).click();
  const deleteDialog = page.locator('.v-overlay-container').filter({ hasText: 'Удалить субсидию' }).first();
  await expect(deleteDialog).toBeVisible();
  await deleteDialog.getByRole('button', { name: /^удалить$/i }).click();
  await expect(deleteDialog).toBeHidden({ timeout: 10_000 });

  await expect(page.locator('.subsidy-card').filter({ hasText: renamedName }), 'карточка не исчезла без reload').toHaveCount(0, { timeout: 10_000 });
  await assertNoLoadingFlicker('удаление субсидии');
  await assertNeighborSameNode('удаление субсидии');
  await page.screenshot({ path: `${SCREEN_DIR}\\subsidy_noflicker_03_deleted.png`, fullPage: true });
});
