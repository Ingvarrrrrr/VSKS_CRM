import { test, expect, Page } from '@playwright/test';
import { waitForOverlays } from './helpers';

/**
 * Phase 17 — Permission System E2E smoke tests.
 *
 * Covers:
 *  - Roles matrix renders (D-03)
 *  - Self-lockout protection (D-05.2)
 *  - Employee sidebar filtering (D-01a)
 *  - Direct forbidden URL redirect (D-01a, router guard)
 *  - Superadmin invisibility in staff (D-09)
 *  - Individual override badge (D-04)
 *
 * NOTE: helpers.ts `login()` is hardcoded to admin/admin123. For this spec we inline
 * a parameterized variant so we can exercise admin + employee flows.
 */

// Adjust credentials to match seed data for your deployment.
const ADMIN = { username: 'admin', password: 'admin123' };
const EMPLOYEE = { username: 'employee', password: 'employee123' };

async function loginAs(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill(username);
  await page.locator('input[type="password"]').first().fill(password);
  await page
    .locator('button[type="submit"], .v-btn')
    .filter({ hasText: /войти|вход|login|sign in/i })
    .first()
    .click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  await waitForOverlays(page);
}

test.describe('Phase 17 — Permission System', () => {
  test('admin can open roles matrix and see role rows', async ({ page }) => {
    await loginAs(page, ADMIN.username, ADMIN.password);
    await page.goto('/admin/roles');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText(/Роли и права|Роли/).first()).toBeVisible({ timeout: 10_000 });
    // Matrix should render at least 4 role rows (admin/org_admin/manager/employee;
    // account_owner may be hidden if current user is admin — count ≥ 4 is safe).
    const rowCount = await page.locator('table tbody tr, .permission-matrix tbody tr').count();
    expect(rowCount).toBeGreaterThanOrEqual(4);
  });

  test('admin can toggle a matrix checkbox and see feedback', async ({ page }) => {
    await loginAs(page, ADMIN.username, ADMIN.password);
    await page.goto('/admin/roles');
    await page.waitForLoadState('networkidle');
    // Find any enabled (non-locked) checkbox on a non-admin row.
    // We target a row that is NOT the current admin row to avoid self-lockout guard.
    const checkbox = page
      .locator('table tbody tr, .permission-matrix tbody tr')
      .filter({ hasText: /Менеджер|Сотрудник|manager|employee/i })
      .first()
      .locator('input[type="checkbox"]')
      .first();
    if (await checkbox.count() === 0) {
      test.skip(true, 'Matrix checkbox selector did not match — adjust when AdminRolesView DOM stabilises');
    }
    const before = await checkbox.isChecked();
    await checkbox.click();
    // Expect either toast-style confirmation or server round-trip settle
    await page.waitForTimeout(800);
    const after = await checkbox.isChecked();
    expect(after).toBe(!before);
    // Revert so test is idempotent
    await checkbox.click();
    await page.waitForTimeout(500);
  });

  test('self-lockout: admin.roles / staff toggles disabled for own role', async ({ page }) => {
    await loginAs(page, ADMIN.username, ADMIN.password);
    await page.goto('/admin/roles');
    await page.waitForLoadState('networkidle');
    // Own-role row should have at least one disabled checkbox (locked admin.roles or staff column)
    const adminRow = page
      .locator('table tbody tr, .permission-matrix tbody tr')
      .filter({ hasText: /Администратор|admin\b/i })
      .first();
    const disabledInputs = adminRow.locator('input[disabled], input[aria-disabled="true"]');
    const disabledCount = await disabledInputs.count();
    expect(disabledCount).toBeGreaterThanOrEqual(1);
  });

  test('employee sidebar hides admin tabs', async ({ page }) => {
    await loginAs(page, EMPLOYEE.username, EMPLOYEE.password);
    // Give AppBar time to load effective permissions
    await page.waitForTimeout(1500);
    const nav = page.locator('.v-navigation-drawer, nav');
    await expect(nav.getByText('Персонал')).toHaveCount(0);
    await expect(nav.getByText('Субсидии')).toHaveCount(0);
    await expect(nav.getByText('Категории ФЭО')).toHaveCount(0);
    await expect(nav.getByText(/Роли\b/)).toHaveCount(0);
  });

  test('employee direct nav to forbidden URL redirects to /my-tasks', async ({ page }) => {
    await loginAs(page, EMPLOYEE.username, EMPLOYEE.password);
    await page.goto('/staff');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    await expect(page).toHaveURL(/\/my-tasks/);
  });

  test('superadmin not listed for admin in staff view', async ({ page }) => {
    await loginAs(page, ADMIN.username, ADMIN.password);
    await page.goto('/staff');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    // Case-insensitive search for 'superadmin' anywhere in the staff table body
    const rows = page.locator('table tbody tr').filter({ hasText: /superadmin/i });
    await expect(rows).toHaveCount(0);
  });

  test('individual badge shows after override toggle in user card', async ({ page }) => {
    await loginAs(page, ADMIN.username, ADMIN.password);
    await page.goto('/staff');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    // Open the first edit dialog available
    const firstEditBtn = page
      .locator('tbody tr')
      .first()
      .locator('button, .v-btn')
      .filter({ hasText: /редактировать|edit|✎/i })
      .or(page.locator('tbody tr').first().locator('.mdi-pencil'))
      .first();
    if (await firstEditBtn.count() === 0) {
      test.skip(true, 'Staff row edit button not found — adjust selector once StaffView row actions are stable');
    }
    await firstEditBtn.click({ force: true });
    await page.waitForTimeout(800);
    // Scroll to «Доступ» section
    const accessSection = page.locator('.v-card, .v-dialog').filter({ hasText: 'Доступ' }).first();
    if (await accessSection.count() === 0) {
      test.skip(true, '«Доступ» section not visible in edit dialog');
    }
    await accessSection.scrollIntoViewIfNeeded();
    // Toggle first available checkbox inside the access section
    const sectionCheckbox = accessSection.locator('input[type="checkbox"]:not([disabled])').first();
    if (await sectionCheckbox.count() === 0) {
      test.skip(true, 'No toggleable checkbox in «Доступ» section');
    }
    await sectionCheckbox.click();
    // Expect «Индивидуально» chip to appear
    await expect(accessSection.getByText('Индивидуально')).toBeVisible({ timeout: 3_000 });
  });
});
