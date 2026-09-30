import { test, expect } from '@playwright/test';
import { login, dismissOrgPicker, waitForOverlays } from './helpers';

test('final stripes verify', async ({ page }) => {
  await login(page).catch(() => {});
  await page.goto('/subsidies');
  await page.waitForLoadState('networkidle').catch(() => {});
  await waitForOverlays(page).catch(() => {});
  await dismissOrgPicker(page).catch(() => {});
  await page.waitForTimeout(1000);

  const link = page.locator('text=МИНПРОС').first();
  await link.click();
  await page.waitForLoadState('networkidle').catch(() => {});
  await waitForOverlays(page).catch(() => {});
  await page.waitForTimeout(1500);

  // Fully purchased: Кубок полуфинал
  const search = page.locator('input[placeholder*="Поиск по субсидии"]').first();
  await search.fill('Кубок полуфинал');
  await page.waitForTimeout(800);
  await page.locator('.feo-search-dropdown__item').first().click();
  await page.waitForTimeout(1000);
  // move mouse away from the row to avoid hover state
  await page.mouse.move(5, 5);
  await page.waitForTimeout(600);
  const fullRow = page.locator('[data-feo-planned-item-id="1438"]');
  await expect(fullRow).toHaveClass(/feo-fully-purchased-row/);
  await fullRow.scrollIntoViewIfNeeded();
  await page.mouse.move(5, 5);
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/stripes-final-fully.png' });

  // Partially purchased: Бинт фиксирующий эластичный ... (Финал variant, id=797)
  await search.fill('');
  await search.fill('Бинт фиксирующий эластичный');
  await page.waitForTimeout(800);
  const items = page.locator('.feo-search-dropdown__item');
  const n = await items.count();
  let clicked = false;
  for (let i = 0; i < n; i++) {
    const txt = await items.nth(i).innerText();
    if (txt.includes('Финал')) { await items.nth(i).click(); clicked = true; break; }
  }
  if (!clicked) await items.first().click();
  await page.waitForTimeout(1000);
  const partRow = page.locator('[data-feo-planned-item-id="797"]');
  await expect(partRow).toHaveClass(/feo-partially-purchased-row/);
  await partRow.scrollIntoViewIfNeeded();
  await page.mouse.move(5, 5);
  await page.waitForTimeout(400);
  await page.screenshot({ path: 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/stripes-final-partial.png' });
});
