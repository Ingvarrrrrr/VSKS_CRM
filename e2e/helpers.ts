import { Page, Locator, APIRequestContext, expect } from '@playwright/test';

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

/**
 * Принимает гейт согласия 152-ФЗ (/consent-required, useConsentGate.ts),
 * если он требуется для текущего пользователя, и жмёт «Принять» на
 * cookie-баннере (CookieBanner.vue), если он показан и перекрывает кнопки.
 * ЕДИНСТВЕННОЕ место в e2e, которое это делает (ПРАВИЛО №6) — вызывается из
 * login() и loginViaApi(), так что все тесты получают обработку сразу, без
 * собственных костылей по страницам.
 *
 * Согласие принимается через тот же API, которым фронт сам пользуется при
 * нажатии «Продолжить» (GET/POST /api/legal/consent-status, /api/legal/consent
 * — см. ConsentRequiredView.vue submit()), а не через клик по чекбоксам в UI:
 * владелец нескольких организаций без поручения получает согласие по одной
 * организации за раз (consent-status отдаёт только первую, см. комментарий
 * в backend/app/routers/legal.py), поэтому цикл повторяет запрос, пока
 * сервер не перестанет его требовать — ровно как делает сама форма.
 */
export async function acceptConsentIfShown(page: Page): Promise<void> {
  const origin = process.env.BASE_URL || 'http://localhost:8079';
  for (let i = 0; i < 5; i++) {
    const statusResp = await page.request.get('/api/legal/consent-status', {
      headers: { Origin: origin },
    }).catch(() => null);
    if (!statusResp || !statusResp.ok()) break;
    const status = await statusResp.json().catch(() => null);
    if (!status || (!status.pd_consent_required && !status.poruchenie_required)) break;
    if (status.pd_consent_required) {
      await page.request.post('/api/legal/consent', {
        headers: { Origin: origin },
        data: { kind: 'pd', accepted: true },
      }).catch(() => {});
    }
    if (status.poruchenie_required && status.poruchenie_org) {
      await page.request.post('/api/legal/consent', {
        headers: { Origin: origin },
        data: { kind: 'poruchenie', accepted: true, org_id: status.poruchenie_org.id },
      }).catch(() => {});
    }
  }
  // Навигация могла уже случиться до вызова этого помощника и застрять на
  // /consent-required — API выше её саму никуда не уводит, нужен reload.
  if (page.url().includes('/consent-required')) {
    await page.reload().catch(() => {});
    await page.waitForLoadState('networkidle').catch(() => {});
  }

  // Cookie-баннер может лежать поверх кнопок формы входа/согласия.
  const cookieBtn = page.locator('.cookie-banner').getByRole('button', { name: 'Принять' });
  if (await cookieBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await cookieBtn.click({ force: true }).catch(() => {});
    await page.waitForTimeout(300);
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
  await acceptConsentIfShown(page);
  await waitForOverlays(page);
  await dismissOrgPicker(page);
}

/**
 * POST /api/auth/login and return the JWT — единственное место, где тесты
 * достают токен для Bearer-авторизации в прямых API-запросах (ПРАВИЛО №6).
 *
 * С 2026-10-13 /api/auth/login больше не кладёт JWT в тело ответа
 * (`access_token` там всегда null — токен живёт только в httpOnly-cookie
 * `gala_session`, см. backend/app/auth/session_cookie.py). Токен достаём из
 * заголовка Set-Cookie (может быть несколько Set-Cookie — читаем через
 * headersArray(), а не headers(), который схлопывает дубликаты), с fallback
 * на body.access_token на случай будущего/иного окружения, где тело всё же
 * его отдаёт.
 *
 * Origin-заголовок ставим ЯВНО и всегда: если вызывающий тест уже делал UI
 * login(page) на этом же page/context, браузерный cookie jar уже несёт
 * gala_session, и CSRF-мидлварь (backend/app/auth/csrf_protection.py) для
 * ЛЮБОГО unsafe-метода с такой cookie требует совпадающий Origin/Referer —
 * даже для самого /auth/login. Без заголовка такой повторный вызов (apiLoginToken
 * через page.request после login(page)) падает 403 "неизвестный источник
 * запроса". APIRequestContext сам Origin не шлёт — ставим его вручную.
 */
export async function apiLoginToken(
  request: APIRequestContext,
  username = 'admin',
  password = 'admin123',
): Promise<string> {
  const origin = process.env.BASE_URL || 'http://localhost:80';
  const resp = await request.post('/api/auth/login', {
    data: { username, password },
    headers: { Origin: origin },
  });
  if (!resp.ok()) {
    throw new Error(`apiLoginToken: POST /api/auth/login вернул ${resp.status()} для ${username}`);
  }
  const setCookieHeaders = resp.headersArray().filter(h => h.name.toLowerCase() === 'set-cookie');
  for (const h of setCookieHeaders) {
    const match = h.value.match(/gala_session=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
  }
  const body = await resp.json().catch(() => ({} as any));
  if (body?.access_token) return body.access_token as string;
  throw new Error('apiLoginToken: JWT не найден ни в Set-Cookie gala_session, ни в body.access_token');
}

/**
 * Кладёт готовый JWT в сессию страницы так же, как это делает реальный логин:
 * cookie `gala_session` (бэкенд читает только её — см. session_cookie.py) +
 * флаг `gala_auth=1` в localStorage (фронт проверяет только его, см.
 * frontend/src/composables/useAuthFlag.ts — сам JWT с 2026-10-13 из JS не
 * читается). Нужно вызывать ДО первого page.goto(), иначе addInitScript не
 * успеет выставить флаг до загрузки роутер-гварда.
 */
export async function applySessionToken(page: Page, token: string, baseURL?: string): Promise<void> {
  const url = baseURL || (page.context() as any)._options?.baseURL || 'http://localhost:8079';
  await page.context().addCookies([{ name: 'gala_session', value: token, url }]);
  await page.addInitScript(() => {
    try { localStorage.setItem('gala_auth', '1'); } catch {}
  });
}

/**
 * Логин без UI-формы: получает JWT через apiLoginToken и сразу раскладывает
 * его как реальную сессию (cookie + флаг) через applySessionToken. Для
 * тестов, которым раньше было достаточно localStorage.setItem('auth_token', ...)
 * перед первым goto. Возвращает токен — пригодится для прямых Bearer-запросов
 * в том же тесте.
 */
export async function loginViaApi(page: Page, username = 'admin', password = 'admin123'): Promise<string> {
  const token = await apiLoginToken(page.request, username, password);
  await applySessionToken(page, token);
  await acceptConsentIfShown(page);
  return token;
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

/**
 * Перетаскивает карточку канбана (CategoryKanbanBoard.vue, components/kanban) —
 * ЕДИНСТВЕННОЕ место в e2e для этого жеста (ПРАВИЛО №6), используется из
 * e2e/35-wish-kanban-dnd-fullscreen.spec.ts и
 * e2e/36-purchase-split-kanban-fullscreen.spec.ts (один и тот же компонент,
 * один и тот же баг).
 *
 * locator.dragTo() там НАДЁЖНО не срабатывает: доска использует vuedraggable
 * (SortableJS) с :force-fallback="true" — JS-имитация drag через обычные
 * mouse-события вместо нативного HTML5 DnD (см. комментарий в
 * CategoryKanbanBoard.vue про зависающий курсор при scroll+native DnD).
 * dragTo() делает mouse.move одним прыжком с внутренней интерполяцией без
 * пауз между кадрами — Sortable с :fallback-tolerance="3" слушает
 * mousemove/pointermove и считает жест начавшимся только когда ПОЛУЧИЛ
 * несколько событий за пределами допуска; одиночный синтетический прыжок
 * Playwright эти промежуточные события не производит в количестве,
 * достаточном для срабатывания фолбэка — drag молча не стартует, карточка
 * остаётся на месте (воспроизведено: e2e/35-...spec.ts несколько прогонов,
 * .wish-card count не меняется ни в исходной, ни в целевой колонке).
 *
 * Фикс — настоящая пошаговая эмуляция мыши: mouse.down → много маленьких
 * mouse.move с paus'ами (даём Sortable обработать каждый кадр через
 * requestAnimationFrame) → mouse.up. Шаг держим не менее fallback-tolerance,
 * иначе первые несколько мс движения не посчитаются за старт drag.
 */
export async function dragCardTo(page: Page, card: Locator, target: Locator): Promise<void> {
  await card.scrollIntoViewIfNeeded();
  const cardBox = await card.boundingBox();
  if (!cardBox) throw new Error('dragCardTo: карточка-источник не видна (boundingBox() вернул null)');
  const startX = cardBox.x + cardBox.width / 2;
  const startY = cardBox.y + cardBox.height / 2;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  // Первое маленькое движение — переводит Sortable (force-fallback) из
  // "mousedown" в режим активного drag, иначе targetBox колонки может ещё не
  // учитывать автоскролл/ререндер, вызванный началом перетаскивания.
  await page.mouse.move(startX + 5, startY + 5, { steps: 3 });
  await page.waitForTimeout(80);

  const targetBox = await target.boundingBox();
  if (!targetBox) throw new Error('dragCardTo: целевая зона не видна (boundingBox() вернул null)');
  const endX = targetBox.x + targetBox.width / 2;
  const endY = targetBox.y + targetBox.height / 2;

  const steps = 14;
  for (let i = 1; i <= steps; i++) {
    const x = startX + (endX - startX) * (i / steps);
    const y = startY + (endY - startY) * (i / steps);
    await page.mouse.move(x, y, { steps: 3 });
    await page.waitForTimeout(40);
  }
  // Задержка на конечной точке — forceFallback вычисляет целевой контейнер
  // через elementFromPoint на следующем animation frame, не синхронно.
  await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForTimeout(200);
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
