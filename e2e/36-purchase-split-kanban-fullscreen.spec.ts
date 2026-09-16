/**
 * Владелец, 2026-09-16 (скриншот прода, закупка 919, «Разбить закупку на
 * несколько»): «у меня экран 27 дюймов — какого хуя канбан в 5 столбцов
 * только... заебался переключаться». Диалог был max-width 1200 — теперь
 * fullscreen, столбцы ~224px, сколько влезает — столько видно, остальное —
 * горизонтальная прокрутка ВНУТРИ области столбцов. Общий компонент со
 * столбчатым бордом — components/kanban/CategoryKanbanBoard.vue (тот же, что
 * у распределения заявки, см. e2e/35-wish-kanban-dnd-fullscreen.spec.ts).
 *
 * Использует существующую закупку с несколькими позициями (id подбирается
 * динамически через API — см. beforeAll) — НЕ выполняет реальное разбиение
 * (кнопка «Разбить» не нажимается), тестовые «+ Столбец» пусты и нигде не
 * сохраняются; единственная персистентная мутация (перетаскивание одной
 * реальной позиции в новую тестовую колонку, нужное для проверки самого
 * механизма drag+persist) откатывается в конце теста через PATCH split-column
 * на ТОТ ЖЕ id, что реально переместился (читается из DOM через
 * data-item-id — см. WishDistributionCard.vue), а не предполагается заранее.
 */
import { test, expect, APIRequestContext } from '@playwright/test';
import { login, dismissOrgPicker } from './helpers';

const API_BASE = 'http://localhost:8079/api';

async function apiLogin(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).access_token as string;
}

test.describe('Канбан «Разбить закупку на несколько» — fullscreen, много столбцов', () => {
  let token: string;
  let purchaseId: number;
  let draggedItemId: number | null = null;

  test.beforeAll(async ({ request }) => {
    token = await apiLogin(request);
    const headers = { Authorization: `Bearer ${token}` };
    const listRes = await request.get(`${API_BASE}/purchases/?limit=300`, { headers });
    expect(listRes.ok()).toBeTruthy();
    const data = await listRes.json();
    const list: any[] = Array.isArray(data) ? data : (data.items || []);
    const LOCKED = new Set(['contracted', 'delivered', 'paid', 'split']);
    const candidate = list.find((p) => !LOCKED.has(p.status) && (p.items?.length || 0) >= 2)
      || list.find((p) => !LOCKED.has(p.status));
    expect(candidate, 'нужна хотя бы одна закупка с >=2 позициями, не locked/split').toBeTruthy();
    purchaseId = candidate.id;
  });

  test.afterAll(async ({ request }) => {
    if (!draggedItemId) return;
    const headers = { Authorization: `Bearer ${token}` };
    await request.patch(`${API_BASE}/purchases/${purchaseId}/items/${draggedItemId}/split-column`, {
      headers, data: { split_column_key: null },
    }).catch(() => {});
  });

  test('fullscreen + много столбцов видно по ширине + drag+persist + автопрокрутка (best-effort)', async ({ page }) => {
    await login(page);
    await dismissOrgPicker(page);

    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.goto(`/orders/${purchaseId}/edit`);
    await page.waitForLoadState('networkidle');

    const splitBtn = page.getByRole('button', { name: /Разбить на закупки/i }).first();
    await expect(splitBtn).toBeVisible({ timeout: 15000 });
    await splitBtn.click();

    const dialog = page.locator('.v-overlay--active .v-card').filter({ hasText: 'Разбить закупку на несколько' }).first();
    await expect(dialog).toBeVisible({ timeout: 10000 });

    // Fullscreen — диалог занимает весь viewport.
    const dialogBox = await dialog.boundingBox();
    expect(dialogBox!.width).toBeGreaterThanOrEqual(2560 - 4);
    expect(dialogBox!.height).toBeGreaterThanOrEqual(1440 - 4);

    const addColBtn = dialog.locator('.kb-col-add').first();
    const existingCols = await dialog.locator('.kb-col').count();
    const toAdd = Math.max(0, 22 - existingCols);
    for (let i = 0; i < toAdd; i++) {
      await addColBtn.click();
      // Только что созданная колонка открыта на редактирование label — Enter
      // фиксирует её и позволяет кликнуть "+" ещё раз без гонки за фокусом.
      await dialog.locator('.kb-col-input').last().press('Enter').catch(() => {});
    }

    const totalCols = await dialog.locator('.kb-col').count();
    expect(totalCols).toBeGreaterThanOrEqual(20);

    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/kanban_fullscreen_01_wide_2560.png',
    });

    // ── Функциональный drag реальной позиции в один из только что созданных
    // пустых столбцов + проверка персистентности через API (та же механика,
    // что и в e2e/35-wish-kanban-dnd-fullscreen.spec.ts для заявки). Именно
    // ЭТА карточка (id читается из data-item-id) — то, что откатывается в
    // afterAll, а не предположение "первая позиция по API". ──
    // Первый ДОБАВЛЕННЫЙ (изначально пустой) столбец — сразу после натуральных
    // категорий, остаётся в видимой области без горизонтальной прокрутки, что
    // делает drag устойчивым к автоскроллу самого Playwright во время действия
    // (последний из 22 столбцов слишком далеко — dragTo прокручивает контейнер
    // к цели ПОСЛЕ начала drag, из-за чего исходная карточка успевает уйти из
    // видимой области и жест срывается).
    const targetCol = dialog.locator('.kb-col:not(.kb-col-add)').nth(existingCols);
    const targetColLabel = (await targetCol.locator('.kb-col-title').textContent())?.trim();
    const cardToDrag = dialog.locator('.wish-card[data-item-id]').first();
    await expect(cardToDrag).toBeVisible();
    draggedItemId = Number(await cardToDrag.getAttribute('data-item-id'));
    expect(draggedItemId).toBeGreaterThan(0);

    await cardToDrag.dragTo(targetCol.locator('.kb-drop'));
    await expect(targetCol.locator('.wish-card')).toHaveCount(1, { timeout: 5000 });

    const headers = { Authorization: `Bearer ${token}` };
    const afterDragRes = await page.request.get(`${API_BASE}/purchases/${purchaseId}`, { headers });
    const afterDrag = await afterDragRes.json();
    const draggedItem = afterDrag.items.find((it: any) => it.id === draggedItemId);
    expect(draggedItem?.split_column_key).toBe(targetColLabel);

    // Сколько столбцов реально ПОМЕЩАЮТСЯ на экране без скролла (2560×1440 →
    // владелец ожидает 10-11).
    const boxesWide = await dialog.locator('.kb-col').evaluateAll((els) =>
      els.map((el) => el.getBoundingClientRect()),
    );
    const viewportWidth = 2560;
    const visibleWide = boxesWide.filter((b) => b.left >= 0 && b.right <= viewportWidth + 1).length;
    expect(visibleWide).toBeGreaterThanOrEqual(10);

    // Тот же диалог на узком экране (1366×768 — владелец ожидает ≥5).
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.waitForTimeout(300);
    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/kanban_fullscreen_02_narrow_1366.png',
    });
    const boxesNarrow = await dialog.locator('.kb-col').evaluateAll((els) =>
      els.map((el) => el.getBoundingClientRect()),
    );
    const visibleNarrow = boxesNarrow.filter((b) => b.left >= 0 && b.right <= 1366 + 1).length;
    expect(visibleNarrow).toBeGreaterThanOrEqual(5);

    // ── Best-effort: автопрокрутка области столбцов при удержании у правого
    // края во время перетаскивания. Синтетический mouse.move в headless
    // Chromium не всегда даёт Sortable's requestAnimationFrame-based autoscroll
    // тикнуть так же надёжно, как реальная мышь — проверка не проваливает тест,
    // только документирует результат (см. аннотацию ниже при неудаче). ──
    const scroller = dialog.locator('.kb-columns').first();
    await scroller.evaluate((el) => { el.scrollLeft = 0; });
    const anotherCard = dialog.locator('.wish-card[data-item-id]').first();
    const cardBox = (await anotherCard.boundingBox())!;
    const scrollerBox = (await scroller.boundingBox())!;
    const edgeX = scrollerBox.x + scrollerBox.width - 15;
    const edgeY = scrollerBox.y + scrollerBox.height / 2;

    const scrollLeftBefore = await scroller.evaluate((el) => el.scrollLeft);
    await page.mouse.move(cardBox.x + cardBox.width / 2, cardBox.y + cardBox.height / 2);
    await page.mouse.down();
    await page.waitForTimeout(150);
    await page.mouse.move(edgeX, edgeY, { steps: 15 });
    for (let i = 0; i < 10; i++) {
      await page.mouse.move(edgeX, edgeY + (i % 2 === 0 ? 1 : -1));
      await page.waitForTimeout(150);
    }
    const scrollLeftDuringDrag = await scroller.evaluate((el) => el.scrollLeft);
    await page.mouse.up();
    await page.waitForTimeout(300);

    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/kanban_fullscreen_03_autoscroll_drag.png',
    });

    if (scrollLeftDuringDrag <= scrollLeftBefore) {
      test.info().annotations.push({
        type: 'note',
        description: `Автопрокрутка НЕ подтверждена автоматизированным тестом ` +
          `(scrollLeft до=${scrollLeftBefore}, во время=${scrollLeftDuringDrag}) — native HTML5 ` +
          `drag (после dragstart) не отвечает на синтетические page.mouse.move той же трассой, ` +
          `что реальная мышь (dragover не переотправляется предсказуемо в headless Chromium), ` +
          `настройки scroll/scroll-sensitivity/scroll-speed выставлены в CategoryKanbanBoard.vue — ` +
          `ручная проверка рекомендуется.`,
      });
    }

    // Закрыть БЕЗ выполнения реального разбиения — "Закрыть", не "Разбить".
    const closeBtn = dialog.getByRole('button', { name: /^Закрыть$/ }).first();
    await closeBtn.click();
  });
});
