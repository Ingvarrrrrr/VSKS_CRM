import { test, expect } from '@playwright/test';
import { login } from './helpers';

const SCREENSHOT_PATH = 'C:/Users/1/AppData/Local/Temp/claude/c--Users-1-Desktop-Cursor-VSKS-CRM/5038739c-4737-4d22-b553-6e587497bd05/scratchpad/dlg-close.png';

test('dialog close button appears and closes dialog', async ({ page }) => {
  await login(page);

  // 1) Товары → Добавить товар (no own close button expected)
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const addBtn = page.getByRole('button', { name: /добавить товар|добавить/i }).first();
  await addBtn.click();
  const dlg1 = page.locator('.v-overlay--active.v-dialog').last();
  await expect(dlg1).toBeVisible({ timeout: 5000 });
  const close1 = dlg1.locator('.hv-dialog-close-btn');
  await expect(close1).toBeVisible({ timeout: 5000 });
  await dlg1.screenshot({ path: SCREENSHOT_PATH });
  await close1.click();
  await expect(dlg1).not.toBeVisible({ timeout: 5000 });

  // 2) Контрагенты dialog
  await page.goto('/contractors');
  await page.waitForLoadState('networkidle');
  const addContractorBtn = page.getByRole('button', { name: /добавить|создать/i }).first();
  if (await addContractorBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await addContractorBtn.click();
    const dlg2 = page.locator('.v-overlay--active.v-dialog').last();
    if (await dlg2.isVisible({ timeout: 5000 }).catch(() => false)) {
      const close2 = dlg2.locator('.hv-dialog-close-btn');
      const visible2 = await close2.isVisible({ timeout: 5000 }).catch(() => false);
      console.log('CONTRACTOR_DIALOG_CLOSE_VISIBLE', visible2);
      if (visible2) {
        await close2.click();
        await expect(dlg2).not.toBeVisible({ timeout: 5000 });
      }
    }
  }

  // 3) Subsidies dialog
  await page.goto('/subsidies');
  await page.waitForLoadState('networkidle');
  const addSubsidyBtn = page.getByRole('button', { name: /добавить|создать|новая/i }).first();
  if (await addSubsidyBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await addSubsidyBtn.click();
    const dlg3 = page.locator('.v-overlay--active.v-dialog').last();
    if (await dlg3.isVisible({ timeout: 5000 }).catch(() => false)) {
      const close3 = dlg3.locator('.hv-dialog-close-btn');
      const visible3 = await close3.isVisible({ timeout: 5000 }).catch(() => false);
      console.log('SUBSIDY_DIALOG_CLOSE_VISIBLE', visible3);
    }
  }
});

test('dialog with own close button does not get a duplicate', async ({ page }) => {
  await login(page);
  await page.goto('/products');
  await page.waitForLoadState('networkidle');
  const addBtn = page.getByRole('button', { name: /добавить товар|добавить/i }).first();
  await addBtn.click();
  const dlg = page.locator('.v-overlay--active.v-dialog').last();
  await expect(dlg).toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(300);
  const count = await dlg.locator('.hv-dialog-close-btn').count();
  console.log('CLOSE_BTN_COUNT', count);
  expect(count).toBeLessThanOrEqual(1);
});
