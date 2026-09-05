import { test, expect, Page } from '@playwright/test';
import { execSync } from 'child_process';
import { login, waitForOverlays } from './helpers';

// e2e/helpers.ts::dismissOrgPicker ищет диалог по тексту 'Выбрать организации',
// а реальный заголовок в AppBar.vue — «Выберите организации» (другая
// словоформа, не подстрока) — helper на эту модалку никогда не срабатывает.
// helpers.ts трогать нельзя (общий файл, вне периметра этой задачи), поэтому
// здесь — свой рабочий дубль с точным текстом.
async function selectOrgAndApply(page: Page) {
  const dialog = page.locator('.v-overlay-container').filter({ hasText: 'Выберите организации' }).first();
  if (!(await dialog.isVisible({ timeout: 2500 }).catch(() => false))) return;
  // Явно организация admin (org_id=1 → «ВСКС»), а НЕ первая по списку — иначе
  // get_org_filter() для superadmin сужает видимость GET /on-shift до выбранной
  // орг, в которую admin может не входить, и диспетчерская карта показывает
  // «никто не на смене» несмотря на реально активную смену. Строка «Выбрать
  // все» — это отдельный <v-checkbox> с @update:model-value, а не @click на
  // всей строке (в отличие от строк отдельных орг) — клик по div-обёртке той
  // строки ничего не переключает, поэтому выбираем конкретную орг по имени.
  const ownOrgRow = dialog.locator('.v-list-item').filter({ hasText: 'ВСКС' }).first();
  await ownOrgRow.click({ force: true });
  await page.waitForTimeout(300);
  const applyBtn = dialog.getByRole('button', { name: /Применить/i });
  if (await applyBtn.isEnabled({ timeout: 1000 }).catch(() => false)) {
    await applyBtn.click({ force: true });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
  }
}

/**
 * Отслеживание местоположения сотрудников (2026-09) — сквозная проверка
 * клиентской части поверх уже готового backend API (staff_location.py).
 *
 * DB-проверки идут напрямую через `docker exec vsks_crm-db-1 psql` — в API
 * нет (и не должно быть) эндпоинта «прочитать сырые строки таблицы», а
 * задание явно требует подтверждать факты запросом к БД, а не доверять UI.
 */

const SCREEN_DIR = 'C:\\Users\\1\\AppData\\Local\\Temp\\claude\\c--Users-1-Desktop-Cursor-VSKS-CRM\\f7c97c55-1f66-4005-ba84-a7c85d9783ca\\scratchpad\\shots_geo';

function psql(sql: string): string {
  const out = execSync(
    `docker exec vsks_crm-db-1 psql -U vsks -d vsks_crm -t -A -c "${sql.replace(/"/g, '\\"')}"`,
    { encoding: 'utf-8' }
  );
  return out.trim();
}

test.describe.serial('Отслеживание местоположения сотрудников', () => {
  test.use({
    permissions: ['geolocation'],
    geolocation: { latitude: 55.7558, longitude: 37.6173 },
  });

  test('0. Стартовое состояние БД — таблицы пусты', async () => {
    expect(psql('select count(*) from staff_shifts')).toBe('0');
    expect(psql('select count(*) from staff_location_points')).toBe('0');
    expect(psql('select count(*) from users')).toBe('41');
  });

  test('1-2. Начало смены → точки уходят на сервер, индикатор виден', async ({ page, context }) => {
    await login(page);
    await selectOrgAndApply(page);
    // Не форсируем повторный goto('/dashboard') сразу после dismissOrgPicker —
    // applyOrgSelection() сам делает window.location.reload(), и гонка с ручным
    // goto() приводила к тому, что попап «Выберите организации» открывался
    // заново (localStorage.selected_org_ids ещё не успел записаться до перезагрузки).
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await waitForOverlays(page);

    // Открыть компактный виджет в шапке
    const chip = page.locator('.stb-chip');
    await expect(chip).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: `${SCREEN_DIR}\\01-before-shift.png` });
    await chip.click();

    const startBtn = page.getByRole('button', { name: 'Я на смене', exact: true });
    await expect(startBtn).toBeVisible({ timeout: 5_000 });
    await startBtn.click();

    // Разрешение уже выдано контекстом Playwright — permission обычно уже
    // 'granted' к этому моменту, объяснение может не показаться. Если оно
    // всё же успело показаться (гонка с refreshPermissionState) — подтверждаем.
    const confirmBtn = page.getByRole('button', { name: 'Начать смену' });
    if (await confirmBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
      await confirmBtn.click();
    }

    await expect(page.locator('.v-snackbar, .gala-toast, [class*="toast"]').filter({ hasText: /Смена начата/i }).first())
      .toBeVisible({ timeout: 10_000 })
      .catch(() => {}); // тост может закрыться раньше проверки — не критично, ниже проверяем факт по БД

    // Индикатор должен показать «На смене»
    await expect(chip.locator('.stb-chip__label')).toHaveText('На смене', { timeout: 15_000 });
    await page.waitForTimeout(1500); // дать первой точке дойти до сервера
    await page.screenshot({ path: `${SCREEN_DIR}\\02-shift-active-indicator.png` });

    // Подтверждение по БД: смена + хотя бы одна точка для admin (id=1)
    expect(psql("select count(*) from staff_shifts where user_id=1 and is_active=true")).toBe('1');
    const pts1 = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');
    expect(pts1).toBeGreaterThanOrEqual(1);

    // ── п.2: смена подставной позиции несколько раз → новые точки приходят ──
    await context.setGeolocation({ latitude: 55.7601, longitude: 37.6186 }); // Кремль → чуть севернее
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);

    await context.setGeolocation({ latitude: 55.7700, longitude: 37.6000 });
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);

    const pts2 = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');
    expect(pts2).toBeGreaterThan(pts1);

    await chip.click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${SCREEN_DIR}\\03-multiple-points-indicator.png` });
    await page.keyboard.press('Escape');
  });

  test('3. Офлайн: точки копятся локально и досылаются после восстановления сети', async ({ page, context }) => {
    await login(page);
    await selectOrgAndApply(page);
    // Не форсируем повторный goto('/dashboard') сразу после dismissOrgPicker —
    // applyOrgSelection() сам делает window.location.reload(), и гонка с ручным
    // goto() приводила к тому, что попап «Выберите организации» открывался
    // заново (localStorage.selected_org_ids ещё не успел записаться до перезагрузки).
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await waitForOverlays(page);

    const beforeOffline = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');

    await context.setOffline(true);
    await context.setGeolocation({ latitude: 55.8000, longitude: 37.5000 });
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);

    // Пока офлайн — новых строк в БД быть не должно (точка осталась в IndexedDB)
    const duringOffline = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');
    expect(duringOffline).toBe(beforeOffline);

    await page.screenshot({ path: `${SCREEN_DIR}\\04-offline-indicator.png` });

    await context.setOffline(false);
    // 'online' listener → flushQueue() немедленно, плюс периодический flush-таймер
    // (20с) как подстраховка. Опрашиваем БД вместо фиксированной паузы — быстрее
    // на «зелёном» прогоне и надёжнее на медленной машине/CI.
    let afterOnline = duringOffline;
    for (let i = 0; i < 20; i++) {
      afterOnline = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');
      if (afterOnline > duringOffline) break;
      await page.waitForTimeout(1000);
    }
    expect(afterOnline).toBeGreaterThan(duringOffline);

    await page.screenshot({ path: `${SCREEN_DIR}\\05-after-reconnect-indicator.png` });
  });

  test('5. Карта диспетчера показывает сотрудника на смене', async ({ page }) => {
    await login(page);
    await selectOrgAndApply(page);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await page.goto('/staff-location');
    await page.waitForLoadState('networkidle');
    await waitForOverlays(page);

    await expect(page.locator('.slm-staff-row').filter({ hasText: 'Администратор' }).first())
      .toBeVisible({ timeout: 15_000 });

    // Клик по строке — открывает карточку с именем и временем последней точки
    await page.locator('.slm-staff-row').filter({ hasText: 'Администратор' }).first().click();
    await expect(page.locator('.slm-popup')).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('.slm-popup__nm')).toContainText('Администратор');
    await page.screenshot({ path: `${SCREEN_DIR}\\06-dispatcher-map-card.png`, fullPage: true });
  });

  test('4. Завершение смены останавливает передачу', async ({ page }) => {
    await login(page);
    await selectOrgAndApply(page);
    // Не форсируем повторный goto('/dashboard') сразу после dismissOrgPicker —
    // applyOrgSelection() сам делает window.location.reload(), и гонка с ручным
    // goto() приводила к тому, что попап «Выберите организации» открывался
    // заново (localStorage.selected_org_ids ещё не успел записаться до перезагрузки).
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    await waitForOverlays(page);

    const chip = page.locator('.stb-chip');
    await chip.click();
    const endBtn = page.getByRole('button', { name: 'Смену закончил', exact: true });
    await expect(endBtn).toBeVisible({ timeout: 5_000 });
    await endBtn.click();

    await expect(chip.locator('.stb-chip__label')).toHaveText('Не на смене', { timeout: 10_000 });

    expect(psql('select count(*) from staff_shifts where user_id=1 and is_active=true')).toBe('0');

    const before = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(1500);
    const after = parseInt(psql('select count(*) from staff_location_points where user_id=1') || '0');
    expect(after).toBe(before); // смена закончена — новых точек нет

    // Карта диспетчера больше не показывает admin как «на смене»
    await page.goto('/staff-location');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('.slm-staff-row').filter({ hasText: 'Администратор' })).toHaveCount(0);
  });

  test('6. Пользователь без права staff.location.view не видит карту (проверка кодом: API + фронт)', async ({ page, request, browser }) => {
    await login(page);
    await selectOrgAndApply(page);

    // Временный сотрудник без права staff.location.view (manager/employee — explicit False в сиде прав)
    const token = await page.evaluate(() => localStorage.getItem('auth_token'));
    const suffix = Date.now();
    const createRes = await request.post('/api/users/', {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        email: `tmp_geo_noperm_${suffix}@example.invalid`,
        password: 'TempPass123!',
        username: `tmp_geo_noperm_${suffix}`,
        role: 'employee',
        last_name: 'Тест',
        first_name: 'БезПрава',
        org_id: 1,
      },
    });
    expect(createRes.ok()).toBeTruthy();
    const created = await createRes.json();
    const tmpUserId = created.id;

    let empContext: Awaited<ReturnType<typeof browser.newContext>> | null = null;
    try {
      // ВАЖНО: отдельный browser context (не page.context().newPage()!) — иначе
      // новая вкладка делит localStorage/сессию с admin, и «логин» временного
      // сотрудника просто остаётся залогинен как admin (проверено — вело к
      // тому, что запрос к /login открывал уже авторизованный дашборд).
      empContext = await browser.newContext();
      const empPage = await empContext.newPage();
      await empPage.goto('/login');
      await empPage.locator('input[type="text"], input[type="email"]').first().fill(`tmp_geo_noperm_${suffix}`);
      await empPage.locator('input[type="password"]').first().fill('TempPass123!');
      await empPage.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход/i }).first().click();
      await empPage.waitForURL(url => !url.pathname.includes('/login'), { timeout: 15_000 });
      await empPage.waitForLoadState('networkidle');

      const empToken = await empPage.evaluate(() => localStorage.getItem('auth_token'));

      // API: 403 напрямую
      const apiRes = await request.get('/api/staff-location/on-shift', {
        headers: { Authorization: `Bearer ${empToken}` },
      });
      expect(apiRes.status()).toBe(403);

      // Frontend: переход на /staff-location уводит редиректом, страница карты не остаётся открытой
      await empPage.goto('/staff-location');
      await empPage.waitForLoadState('networkidle');
      await empPage.waitForTimeout(500);
      expect(empPage.url()).not.toContain('/staff-location');

      // «Моё местоположение» при этом доступно — свои данные без права
      const myLastRes = await request.get('/api/staff-location/mine/last', {
        headers: { Authorization: `Bearer ${empToken}` },
      });
      expect(myLastRes.ok()).toBeTruthy();

    } finally {
      if (empContext) await empContext.close().catch(() => {});
      // Уборка временного пользователя
      await request.delete(`/api/users/${tmpUserId}`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { confirm: 'true' },
      });
    }
  });

  test('7. Уборка тестовых данных смен/точек', async () => {
    psql('delete from staff_location_points');
    psql('delete from staff_shifts');
    expect(psql('select count(*) from staff_shifts')).toBe('0');
    expect(psql('select count(*) from staff_location_points')).toBe('0');
    expect(psql('select count(*) from users')).toBe('41');
  });
});
