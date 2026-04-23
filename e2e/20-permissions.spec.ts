import { test, expect } from '@playwright/test';
import { login } from './helpers';

test.describe('Permissions system (Phase 17)', () => {

  test.skip(({}, testInfo) => true, 'Pending Plans 17-06/07/08');

  test('matrix renders for admin', async ({ page }) => {
    await login(page, 'admin', 'admin');
    await page.goto('/admin/roles');
    await expect(page.getByText('Роли')).toBeVisible();
    await expect(page.locator('table')).toBeVisible();
  });

  test('individual badge appears after override', async ({ page }) => {
    await login(page, 'admin', 'admin');
    await page.goto('/staff');
    // TODO: flip a checkbox in user card, confirm «Индивидуально» chip replaces role chip
  });

  test('nav hides staff tab for employee', async ({ page }) => {
    await login(page, 'employee', 'employee');
    await expect(page.locator('nav').getByText('Персонал')).toHaveCount(0);
  });
});
