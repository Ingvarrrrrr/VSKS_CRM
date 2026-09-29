import { test } from '@playwright/test';
import { login, waitForOverlays } from './helpers';

test('fully-purchased stripe/legend/toggle screenshots', async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  await page.goto('/subsidies');
  await page.waitForLoadState('networkidle');
  await waitForOverlays(page);
  await page.waitForTimeout(1000);

  // SubsidyListTable.vue: clicking the subsidy name span (font-weight-medium
  // cursor-pointer) toggles selection and opens the detail/FEO tree panel.
  // МИНПРОС_2026 (id=51) has both fully- and partially-purchased plan
  // positions in this dataset (checked via GET /feo-categories/plan-positions).
  await page.getByText('МИНПРОС_2026', { exact: true }).first().click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await waitForOverlays(page);

  const legend = page.locator('.feo-fully-purchased-legend').first();
  await legend.scrollIntoViewIfNeeded().catch(() => {});
  await page.screenshot({ path: 'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\5038739c-4737-4d22-b553-6e587497bd05\\scratchpad\\plan-done-1-tree-legend.png', fullPage: false });

  // Use the built-in tree search (useFeoTreeSearch.ts) to jump straight to a
  // plan position known (via GET /feo-categories/plan-positions) to be fully
  // purchased in this dataset, instead of blindly expanding categories.
  const searchInput = page.locator('.feo-search-wrap input').first();
  await searchInput.fill('Огнетушитель ОУ-2').catch(() => {});
  await page.waitForTimeout(1000);
  const searchResult = page.locator('.feo-search-dropdown__item').first();
  if (await searchResult.isVisible({ timeout: 3000 }).catch(() => false)) {
    await searchResult.click().catch(() => {});
    await page.waitForTimeout(1500);
  }
  await waitForOverlays(page);
  const panel = page.locator('[data-feo-panel-for]').first();
  await panel.scrollIntoViewIfNeeded().catch(() => {});
  await page.screenshot({ path: 'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\5038739c-4737-4d22-b553-6e587497bd05\\scratchpad\\plan-done-2-level5-panel.png', fullPage: false });

  // Toggle "hide fully purchased"
  const toggle = page.locator('.feo-fully-purchased-legend .v-switch').first();
  await toggle.scrollIntoViewIfNeeded().catch(() => {});
  if (await toggle.isVisible({ timeout: 3000 }).catch(() => false)) {
    await toggle.click().catch(() => {});
    await page.waitForTimeout(800);
  }
  await page.screenshot({ path: 'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\5038739c-4737-4d22-b553-6e587497bd05\\scratchpad\\plan-done-3-hidden-toggle.png', fullPage: false });
});
