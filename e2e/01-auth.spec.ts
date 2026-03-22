import { test, expect } from '@playwright/test';

test.describe('Аутентификация', () => {
  test('Лендинг загружается', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Should show landing page with login/register buttons
    const body = await page.textContent('body');
    expect(body).toBeTruthy();
    // Check there are no crash screens
    await expect(page.locator('#app')).toBeVisible();
  });

  test('Страница логина загружается', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    // Should have email/login and password fields
    const inputs = page.locator('input');
    await expect(inputs.first()).toBeVisible();
  });

  test('Неудачный логин показывает ошибку', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.locator('input[type="text"], input[type="email"]').first().fill('wrong_user');
    await page.locator('input[type="password"]').first().fill('wrong_pass');
    await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
    await page.waitForTimeout(2000);
    // Should still be on login page or show error
    const url = page.url();
    const hasError = await page.locator('.v-alert, .v-snackbar, .error').first().isVisible().catch(() => false);
    expect(url.includes('/login') || hasError).toBeTruthy();
  });

  test('Успешный логин admin/admin123', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
    await page.locator('input[type="password"]').first().fill('admin123');
    await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
    await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
    // Should redirect to dashboard
    expect(page.url()).not.toContain('/login');
  });

  test('Страница регистрации загружается', async ({ page }) => {
    await page.goto('/register');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('input').first()).toBeVisible();
  });
});
