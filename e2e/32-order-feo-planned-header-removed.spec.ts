/**
 * Верификация задачи 2026-08-21 (п.6, CreateOrderView.vue): шапочный
 * read-only перечень плановых позиций категории (headPlannedListItems) убран
 * — дублировал построчный FeoPlannedItemsSelect. Открывает существующую
 * закупку id=886 (subsidy_id=7, feo_category_id=125, feo_per_item=false —
 * «одна категория на всю закупку», реальные прод-данные, ничего не создаёт
 * и не удаляет).
 */
import { test, expect, Page } from '@playwright/test';

async function doLogin(page: Page) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15_000 });
  await page.evaluate(() => {
    localStorage.setItem('selected_org_ids', JSON.stringify([1]));
    localStorage.setItem('selected_org_names', JSON.stringify(['ВСКС']));
  });
}

test('Шапочный перечень плановых позиций закупки убран; построчный работает', async ({ page }) => {
  await doLogin(page);
  await page.goto('/orders/886');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);

  // Header list heading text ("Плановые позиции категории") must be gone entirely.
  const headHeading = page.getByText('Плановые позиции категории', { exact: false });
  await expect(headHeading).toHaveCount(0);

  // The switch label is renamed too.
  const switchLabel = page.getByText('Разные категории ФЭО для каждого товара', { exact: true });
  await expect(switchLabel.first()).toBeVisible();
  const switchInput = page.locator('.v-switch input[type="checkbox"]').first();
  await expect(switchInput).not.toBeChecked();

  // Per-row planned selector must be available even in single-category mode.
  // Stages layout (ТЗ/Договор/Поставка expand-row) — the feo-attrs area only
  // renders once the row is expanded.
  const expandAllBtn = page.locator('.v-btn').filter({ hasText: /Развернуть всё/ }).first();
  await expandAllBtn.scrollIntoViewIfNeeded().catch(() => {});
  await expandAllBtn.click().catch(() => {});
  await page.waitForTimeout(800);
  const denseCount = await page.locator('.feo-planned-dense-row').count();
  console.log('  dense plan selectors in single-category mode:', denseCount);
  expect(denseCount, 'Построчный выбор плановой должен быть у позиций закупки в режиме «одна на всех»').toBeGreaterThan(0);

  await page.screenshot({ path: 'e2e-report/32-order-single-category.png', fullPage: true }).catch(() => {});
});
