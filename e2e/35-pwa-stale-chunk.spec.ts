import { test, expect } from '@playwright/test';
import { login } from './helpers';

// Прод-инцидент 2026-09-16: сразу после деплоя владелец видел только логотип
// «G» посреди пустого экрана. Механизм (см. отчёт сессии): пользователь уже
// открыл вкладку СО СТАРЫМ JS-бандлом в памяти; во время нового деплоя старые
// хэшированные чанки (Vue Router `() => import(...)` для ленивых роутов)
// пропадают с сервера; клик на ещё не подгруженный роут кидает динамический
// import() в 404 → браузер бросает 'vite:preloadError' → ДО фикса никто эту
// ошибку не ловил (index.html self-heal реагирует только на статические
// <script>/<link>, не на dynamic import()) → роут не монтируется →
// пользователь навсегда видит только статическую разметку index.html
// (#app:empty::after — фон + логотип), без авто-починки.
//
// Репродукция через page.route(), а не второй docker build/удаление файлов
// в контейнере: имитирует РОВНО ту же ошибку браузера (реальный 404 на JS
// URL ленивого чанка) детерминированно и без гонки с nginx round-robin
// между frontend_a/frontend_b (upstream frontend_pool, nginx/nginx.conf) —
// какой из двух контейнеров реально отдал бы 404, эмулировать не нужно,
// значение имеет только то, что видит браузер.
//
// Один прогон = один режим:
//   PWA_TEST_MODE=before — код ДО фикса (main.ts/vite.config/custom-sw.js
//     без обработчика vite:preloadError) — ожидаем зависшую пустую страницу.
//   PWA_TEST_MODE=after  — код ПОСЛЕ фикса — ожидаем один авто-reload и
//     живое приложение после него (не обязательно на /billing — см. ниже).
// Какой код сейчас развёрнут в docker решает не тест — см. отчёт сессии.

const MODE = process.env.PWA_TEST_MODE === 'after' ? 'after' : 'before';
const SCREENSHOT = process.env.PWA_SCREENSHOT_PATH ||
  `C:\\Users\\1\\Documents\\VAULT_for_LLM\\Projects\\VSKS_CRM\\Artifacts\\pwa_stale_${MODE}.png`;

test('деплой во время открытой вкладки: устаревший ленивый чанк', async ({ page }) => {
  test.setTimeout(60_000);

  // 1. Обычный вход — вкладка загружает бандл и держит его в памяти на всё
  //    время теста, как реальный пользователь с открытой вкладкой.
  await login(page);

  // 2. Симулируем деплой: ПЕРВЫЙ запрос JS-чанка «Биллинг» получает 404
  //    (файл по старому хэшу пропал с сервера), любой повторный запрос (уже
  //    после авто-reload на свежий бандл) проходит нормально.
  let failedOnce = false;
  await page.route('**/assets/BillingView-*.js', async (route) => {
    if (!failedOnce) {
      failedOnce = true;
      await route.fulfill({ status: 404, contentType: 'text/plain', body: 'Not Found' });
      return;
    }
    await route.continue();
  });

  const consoleErrors: string[] = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

  // Маркер переживает клиентскую навигацию (SPA, тот же `window`), но
  // ИСЧЕЗАЕТ при полной перезагрузке страницы — так отличаем «фикс дошёл до
  // reload» от «ничего не произошло, страница просто осталась как была».
  // Важно: Vue Router абортит навигацию ДО смены URL, если ленивый компонент
  // не резолвится (см. 'before' — finalUrl остаётся /dashboard) — то есть
  // recovery-reload воспроизведёт ТЕКУЩИЙ (последний успешный) route, а не
  // домчит пользователя до /billing автоматически. Это и есть корректное
  // поведение самолечения: почини вкладку, а не «доделай то, что не вышло».
  await page.evaluate(() => { (window as any).__preReloadMarker = Date.now(); });

  // 3. Клиентская навигация (НЕ page.goto — тот дал бы полный переход и
  //    свежий index.html; нужен именно router-link клик той же вкладкой,
  //    чтобы дёрнуть dynamic import() уже загруженного бандла).
  await page.locator('a[href="/billing"]').first().click({ force: true, timeout: 5000 });

  if (MODE === 'after') {
    // Фикс должен поймать 'vite:preloadError', вычистить SW/кэши и
    // перезагрузить страницу один раз.
    await page.waitForTimeout(2500);
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1000);
  } else {
    // ДО фикса — ничего не происходит само, просто ждём и фиксируем факт.
    await page.waitForTimeout(4000);
  }

  await page.screenshot({ path: SCREENSHOT, fullPage: true });

  const appIsEmpty = await page.evaluate(() => {
    const app = document.getElementById('app');
    return !app || app.children.length === 0;
  });
  // Заголовок BillingView.vue ("<h2>Биллинг</h2>" внутри контентной зоны) —
  // не текст сайдбар-ссылки, который присутствует в DOM независимо от роута.
  const billingRendered = await page.locator('main h2', { hasText: 'Биллинг' }).first()
    .isVisible({ timeout: 2000 }).catch(() => false);
  // undefined после reload (свежий window), сохраняет значение при простом
  // зависании без перезагрузки.
  const reloadHappened = await page.evaluate(() => (window as any).__preReloadMarker === undefined);
  // Дашборд (или любой другой ранее рабочий route) снова живой после reload —
  // не застрял на бесконечных skeleton-заглушках из-за брошенного запроса.
  const dashboardAlive = await page.locator('main').filter({ hasText: /Дашборд|Биллинг/ }).first()
    .isVisible({ timeout: 3000 }).catch(() => false);

  console.log(JSON.stringify({
    MODE,
    appIsEmpty,
    billingRendered,
    reloadHappened,
    dashboardAlive,
    finalUrl: page.url(),
    consoleErrorsSample: consoleErrors.slice(0, 8),
  }, null, 2));

  if (MODE === 'before') {
    // Документируем баг: приложение застряло — либо #app пуст (логотип из
    // #app:empty::after), либо просто ничего само не восстановилось (нет
    // reload) — ни то, ни другое не должно требовать проверки на "before".
    expect(reloadHappened).toBeFalsy();
  } else {
    // Фикс сработал: страница реально перезагрузилась сама (не просто
    // осталась висеть) и после этого приложение снова живое, не пустое.
    expect(reloadHappened).toBeTruthy();
    expect(appIsEmpty).toBeFalsy();
    expect(dashboardAlive).toBeTruthy();
  }
});
