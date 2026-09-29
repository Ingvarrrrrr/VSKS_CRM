// Временный приёмочный e2e для бага владельца (29.09): переключатель
// таблица/карточки на странице «Субсидии» не менял вид без F5 (см.
// frontend/src/composables/subsidies/ctxSingleton.ts — SubsidyListHeader.vue
// и соседние дочерние компоненты пересобирали singleton useSubsidyList() с
// другим ctx, чем SubsidiesView.vue, поэтому клик по переключателю менял
// «осиротевшую» копию viewMode, а не ту, что читает v-if в шаблоне).
//
// Сценарий: переключить вид туда-обратно БЕЗ перезагрузки страницы, затем
// уйти на другую страницу и вернуться — выбор должен сохраниться (уже
// работавшее поведение localStorage, не должно сломаться фиксом).
import { test, expect } from '@playwright/test';
import { login } from './helpers';

test('переключатель вида субсидий (таблица/карточки) работает без F5', async ({ page }) => {
  await login(page);
  await page.goto('/subsidies');
  await page.waitForLoadState('networkidle');

  const table = page.locator('table').first();
  const toggle = page.locator('.v-btn-toggle').filter({ has: page.locator('.mdi-table') }).first();
  const cardsBtn = toggle.locator('button').filter({ has: page.locator('.mdi-view-grid') }).first();
  const tableBtn = toggle.locator('button').filter({ has: page.locator('.mdi-table') }).first();

  // Убедиться, что стартовое состояние — таблица (или переключить явно).
  await tableBtn.click();
  await page.waitForTimeout(300);
  await expect(table).toBeVisible();

  // Переключить на карточки — БЕЗ перезагрузки страницы.
  await cardsBtn.click();
  await page.waitForTimeout(300);
  await expect(table).toBeHidden();
  const cardsGrid = page.locator('.subsidy-card').first();
  await expect(cardsGrid).toBeVisible({ timeout: 5000 });

  // И обратно на таблицу — тоже без перезагрузки.
  await tableBtn.click();
  await page.waitForTimeout(300);
  await expect(table).toBeVisible();
  await expect(cardsGrid).toBeHidden();

  // Переключить на карточки, уйти на другую страницу и вернуться — выбор
  // должен остаться «карточки» (localStorage-персист, старое поведение).
  await cardsBtn.click();
  await page.waitForTimeout(300);
  await expect(cardsGrid).toBeVisible({ timeout: 5000 });

  await page.goto('/orders');
  await page.waitForLoadState('networkidle');
  await page.goto('/subsidies');
  await page.waitForLoadState('networkidle');

  await expect(page.locator('.subsidy-card').first()).toBeVisible({ timeout: 5000 });
  await expect(page.locator('table').first()).toBeHidden();
});
