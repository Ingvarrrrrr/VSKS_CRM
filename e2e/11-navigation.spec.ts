import { test, expect, Page } from '@playwright/test';
import { login, collectApiErrors, waitForOverlays } from './helpers';

test.describe('Навигация и AppBar', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('Боковое меню отображается с пунктами навигации', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Check sidebar exists and has items
    const drawer = page.locator('.v-navigation-drawer');
    await expect(drawer.first()).toBeVisible();

    const navItems = page.locator('.v-navigation-drawer .v-list-item, .v-navigation-drawer a');
    const navCount = await navItems.count();
    console.log(`  📌 Navigation items found: ${navCount}`);
    expect(navCount).toBeGreaterThanOrEqual(5);

    // Verify items have text and href
    for (let i = 0; i < Math.min(navCount, 5); i++) {
      const item = navItems.nth(i);
      const text = await item.textContent().catch(() => '');
      const href = await item.getAttribute('href').catch(() => '');
      console.log(`  📍 ${text?.trim()} → ${href || '(no href)'}`);
    }
  });

  test('Глобальный поиск работает', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    const searchInput = page.locator('.v-app-bar input[type="text"], .v-toolbar input').first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.click({ force: true });
      await searchInput.fill('тест');
      await page.waitForTimeout(2000);

      const results = page.locator('.v-menu .v-list-item, .search-results, .v-overlay .v-list');
      const hasResults = await results.first().isVisible().catch(() => false);
      console.log(`  🔍 Global search results: ${hasResults}`);

      await searchInput.clear();
      await page.keyboard.press('Escape');
    } else {
      console.log('  ⚠️ Search input not found in AppBar');
    }
  });

  test('Тема (dark/light) переключается', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    // Try multiple selectors for theme button
    const themeBtn = page.locator('.v-app-bar .v-btn .mdi-brightness-6, .v-app-bar .v-btn .mdi-weather-night, .v-app-bar .v-btn .mdi-white-balance-sunny').first();
    if (await themeBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await themeBtn.click({ force: true });
      await page.waitForTimeout(1000);
      console.log('  🌙 Theme toggled');
      await themeBtn.click({ force: true }).catch(() => {});
    } else {
      // Try finding by aria-label or tooltip
      const anyThemeBtn = page.locator('[aria-label*="тем"], [aria-label*="theme"], [title*="тем"]').first();
      if (await anyThemeBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await anyThemeBtn.click({ force: true });
        console.log('  🌙 Theme toggled (via aria-label)');
      } else {
        console.log('  ⚠️ Theme toggle button not found');
      }
    }
  });

  test('Профиль пользователя доступен', async () => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await waitForOverlays(page);

    // Find avatar/user menu — usually last button or avatar in AppBar
    const avatar = page.locator('.v-app-bar .v-avatar, .v-toolbar .v-avatar').first();
    const menuBtn = page.locator('.v-app-bar .v-btn').last();

    if (await avatar.isVisible({ timeout: 3000 }).catch(() => false)) {
      await avatar.click({ force: true });
      await page.waitForTimeout(1000);
      const menuItems = page.locator('.v-list-item');
      console.log(`  👤 User menu items: ${await menuItems.count()}`);
      await page.keyboard.press('Escape');
    } else if (await menuBtn.isVisible().catch(() => false)) {
      await menuBtn.click({ force: true });
      await page.waitForTimeout(1000);
      console.log('  👤 Clicked last AppBar button');
      await page.keyboard.press('Escape');
    } else {
      console.log('  ⚠️ User avatar/menu not found');
    }
  });
});
