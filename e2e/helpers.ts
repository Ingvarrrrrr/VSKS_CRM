import { Page, expect } from '@playwright/test';

/**
 * Dismiss the global org picker ("Выберите организации") if it pops up after
 * login. Persistent for superadmin accounts with many orgs — its scrim blocks
 * all clicks until an org selection is applied. Idempotent: no-op if the
 * dialog isn't showing.
 *
 * NB: the dialog title is «Выберите организации» (not «Выбрать организации» —
 * different word form, not a substring match).
 */
export async function dismissOrgPicker(page: Page) {
  const dialog = page.locator('.v-overlay-container').filter({ hasText: 'Выберите организации' }).first();
  if (!(await dialog.isVisible({ timeout: 1500 }).catch(() => false))) {
    return;
  }
  // "Выбрать все" is a <v-checkbox> driven by @update:model-value on the
  // checkbox itself, not a @click on the row (unlike individual org rows) —
  // clicking the v-list-item div does nothing. Click the checkbox's own
  // control wrapper instead.
  const selectAllRow = dialog.locator('.v-list-item').first();
  const selectAllWrapper = selectAllRow.locator('.v-selection-control__wrapper').first();
  await selectAllWrapper.click({ force: true }).catch(() => {});
  await page.waitForTimeout(200);
  const applyBtn = dialog.getByRole('button', { name: /Применить/i });
  if (await applyBtn.isEnabled({ timeout: 1000 }).catch(() => false)) {
    await applyBtn.click({ force: true });
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(500);
  } else {
    // Fallback: press Escape
    await page.keyboard.press('Escape');
  }
}

/** Wait for Vuetify overlays to disappear */
export async function waitForOverlays(page: Page) {
  // Wait for v-overlay__scrim to disappear (loading overlays, etc.)
  await page.waitForTimeout(500);
  try {
    await page.waitForFunction(() => {
      const scrims = document.querySelectorAll('.v-overlay__scrim');
      return scrims.length === 0 || Array.from(scrims).every(s => {
        const style = getComputedStyle(s);
        return style.display === 'none' || style.opacity === '0' || style.visibility === 'hidden';
      });
    }, { timeout: 5000 });
  } catch {
    // If overlay persists, try clicking it to dismiss
    const scrim = page.locator('.v-overlay__scrim').first();
    if (await scrim.isVisible().catch(() => false)) {
      await scrim.click({ force: true }).catch(() => {});
      await page.waitForTimeout(500);
    }
  }
}

/** Login as admin and return authenticated page */
export async function login(page: Page) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login|sign in/i }).first().click();
  // Wait for redirect to dashboard or any authenticated page
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  await waitForOverlays(page);
  await dismissOrgPicker(page);
}

/** Collect console errors during a callback */
export async function collectConsoleErrors(page: Page, fn: () => Promise<void>): Promise<string[]> {
  const errors: string[] = [];
  const handler = (msg: any) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  };
  page.on('console', handler);
  await fn();
  page.off('console', handler);
  return errors;
}

/** Navigate to a route and wait for load */
export async function navigateTo(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  // Wait a bit for Vue to render
  await page.waitForTimeout(1000);
}

/** Check for uncaught JS errors on a page */
export async function checkPageErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('pageerror', (err) => {
    errors.push(err.message);
  });
  return errors;
}

/** Click a button by text safely (handles Vuetify overlays) */
export async function clickButton(page: Page, text: string | RegExp) {
  await waitForOverlays(page);
  const btn = page.locator('.v-btn, button').filter({ hasText: text }).first();
  if (await btn.isVisible({ timeout: 3000 }).catch(() => false)) {
    try {
      await btn.click({ timeout: 5000 });
    } catch {
      // If overlay blocks, force click
      await btn.click({ force: true });
    }
    await page.waitForTimeout(500);
    return true;
  }
  return false;
}

/** Check for API errors (4xx/5xx) */
export function collectApiErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('response', (response) => {
    if (response.status() >= 400) {
      errors.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });
  return errors;
}
