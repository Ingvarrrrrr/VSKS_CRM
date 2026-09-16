/**
 * Владелец, 2026-09-16 (прод): три жалобы на канбан «Распределить и одобрить»
 * (заявки) и «Разбить закупку на несколько»:
 *  1) drag-and-drop карточек по колонкам сломан при рефакторинге WishesView
 *     (commit 8091b92d) — на деле пережил перенос в WishDistributionKanban.vue,
 *     но не имел ни «+ Столбец», ни полноэкранного окна;
 *  2) нужна возможность создавать новые столбцы;
 *  3) кнопка «Распределить» не видна для уже одобренной (approved) заявки;
 *  4) окно узкое — на 27" видно 5 столбцов из 26;
 *  5) перекидывание по колонкам «слетает», если случайно закрыть окно.
 *
 * Этот файл проверяет все пять пунктов через API-подготовку данных (быстрее и
 * надёжнее UI-заведения заявки/закупки) + управление самим канбаном через UI.
 */
import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { login, dismissOrgPicker } from './helpers';

const API_BASE = 'http://localhost:8079/api';

async function apiLogin(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: { username: 'admin', password: 'admin123' },
  });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  return body.access_token as string;
}

async function authed(request: APIRequestContext, token: string) {
  return { Authorization: `Bearer ${token}` };
}

test.describe('Канбан «Распределить и одобрить» (заявки) — DnD, +Столбец, fullscreen, approved', () => {
  let token: string;
  let wishId: number;
  let catA: string;
  let catB: string;

  test.beforeAll(async ({ request }) => {
    token = await apiLogin(request);
    const headers = await authed(request, token);

    // Два товара из каталога с РАЗНЫМИ категориями — чтобы канбан сразу
    // построил 2 РЕАЛЬНЫЕ колонки (не только "+ Столбец").
    const productsRes = await request.get(`${API_BASE}/products/?limit=500`, { headers });
    expect(productsRes.ok()).toBeTruthy();
    const products: any[] = await productsRes.json();
    const byCategory = new Map<string, any>();
    for (const p of products) {
      const cat = (p.category || '').trim();
      if (cat && !byCategory.has(cat)) byCategory.set(cat, p);
      if (byCategory.size >= 2) break;
    }
    expect(byCategory.size).toBeGreaterThanOrEqual(2);
    const [[cA, prodA], [cB, prodB]] = [...byCategory.entries()];
    catA = cA;
    catB = cB;

    const createRes = await request.post(`${API_BASE}/wishes/`, {
      headers,
      data: {
        title: 'E2E kanban DnD test wish (temp)',
        items: [
          { item_name: prodA.name, product_id: prodA.id, item_type: 'товар', quantity: 1, unit: 'шт', unit_price: 100, total_price: 100 },
          { item_name: prodB.name, product_id: prodB.id, item_type: 'товар', quantity: 1, unit: 'шт', unit_price: 100, total_price: 100 },
          { item_name: 'Третья позиция без категории (temp)', item_type: 'товар', quantity: 1, unit: 'шт', unit_price: 50, total_price: 50 },
        ],
      },
    });
    expect(createRes.ok()).toBeTruthy();
    const wish = await createRes.json();
    wishId = wish.id;

    // submit_wish (wish_transitions.py) 409-ит без хотя бы одного согласующего —
    // назначаем admin (user_id=1) самому себе, тот же путь, что кнопка
    // «Добавить согласующего» в карточке.
    const addApproverRes = await request.post(`${API_BASE}/wishes/${wishId}/approvers`, {
      headers,
      data: { user_id: 1 },
    });
    expect(addApproverRes.ok()).toBeTruthy();

    const submitRes = await request.post(`${API_BASE}/wishes/${wishId}/submit`, { headers });
    expect(submitRes.ok()).toBeTruthy();
  });

  test.afterAll(async ({ request }) => {
    // Тестовые данные — удаляем созданную заявку целиком (не «возвращаем как
    // было», т.к. она не существовала до теста).
    if (wishId) {
      const headers = await authed(request, token);
      await request.delete(`${API_BASE}/wishes/${wishId}`, { headers }).catch(() => {});
    }
  });

  test('DnD между колонками сохраняется, окно fullscreen, "+ Столбец" работает, переживает закрытие', async ({ page }) => {
    await login(page);
    await dismissOrgPicker(page);
    await page.goto('/wishes');
    await page.waitForLoadState('networkidle');

    // Найти нашу тестовую заявку на вкладке «Мои» и открыть «Распределить».
    const row = page.locator('tr', { hasText: 'E2E kanban DnD test wish' }).first();
    await row.scrollIntoViewIfNeeded();
    const distributeBtn = row.getByRole('button', { name: /^Распределить$/ }).first();
    await expect(distributeBtn).toBeVisible({ timeout: 10000 });
    await distributeBtn.click();

    const dialog = page.locator('.v-overlay--active .v-card').filter({ hasText: 'Распределение позиций по закупкам' }).first();
    await expect(dialog).toBeVisible({ timeout: 10000 });

    // fullscreen: диалог занимает всё окно (владелец, 27" — «26 столбцов, видно 5»).
    const dialogBox = await dialog.boundingBox();
    const viewport = page.viewportSize()!;
    expect(dialogBox).not.toBeNull();
    expect(dialogBox!.width).toBeGreaterThanOrEqual(viewport.width - 4);
    expect(dialogBox!.height).toBeGreaterThanOrEqual(viewport.height - 4);

    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/wish_kanban_01_fullscreen_before_dnd.png',
    });

    const colA = dialog.locator('.kb-col', { hasText: catA }).first();
    const colB = dialog.locator('.kb-col', { hasText: catB }).first();
    await expect(colA).toBeVisible();
    await expect(colB).toBeVisible();

    const cardA = colA.locator('.wish-card').first();
    await expect(cardA).toBeVisible();

    // ── Drag карточки из колонки A в колонку B: vuedraggable/Sortable (native
    // HTML5 DnD, forceFallback НЕ используется — см. CategoryKanbanBoard.vue)
    // отвечает на настоящие dragstart/dragover/drop, которые эмулирует
    // Playwright'овский locator.dragTo(). ──
    const cardBoxCountBefore = await colB.locator('.wish-card').count();

    const patchResponse = page.waitForResponse(
      (r) => r.url().includes(`/api/wishes/${wishId}/items/`) && r.request().method() === 'PATCH',
      { timeout: 15000 },
    ).catch(() => null);

    await cardA.dragTo(colB.locator('.kb-drop'));
    await page.waitForTimeout(300);
    const resp = await patchResponse;

    // Карточка теперь физически в колонке B: было cardBoxCountBefore (её
    // собственная "естественная" позиция), стало +1 (пришла из colA), а colA
    // опустела. Строгая проверка обоих концов — раньше здесь была слабая
    // проверка «colB.count===1», которая была true ДО любого drag (колонка и
    // так стартовала с 1 карточкой) и маскировала полностью нерабочий drag.
    await expect(colB.locator('.wish-card')).toHaveCount(cardBoxCountBefore + 1, { timeout: 5000 });
    await expect(colA.locator('.wish-card')).toHaveCount(0, { timeout: 5000 });
    if (resp) {
      expect(resp.ok()).toBeTruthy();
    }

    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/wish_kanban_02_after_dnd.png',
    });

    // ── «+ Столбец» ──
    const addColBtn = dialog.locator('.kb-col-add').first();
    await addColBtn.click();
    const newColInput = dialog.locator('.kb-col-input').first();
    await expect(newColInput).toBeVisible();
    await newColInput.fill('E2E temp column');
    await newColInput.press('Enter');
    const newCol = dialog.locator('.kb-col', { hasText: 'E2E temp column' }).first();
    await expect(newCol).toBeVisible();

    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/wish_kanban_03_new_column.png',
    });

    // Закрыть окно крестиком (Esc-путь) — картиночная позиция из "Не определено"
    // не трогалась, а «E2E temp column» пустая: должно появиться предупреждение.
    await page.keyboard.press('Escape');
    const warningSnack = page.locator('.toast-item').filter({ hasText: /не сохранится/i }).first();
    await expect(warningSnack).toBeVisible({ timeout: 5000 });

    // ── Переоткрыть окно — перемещённая карточка должна остаться в colB. ──
    await distributeBtn.click();
    const dialog2 = page.locator('.v-overlay--active .v-card').filter({ hasText: 'Распределение позиций по закупкам' }).first();
    await expect(dialog2).toBeVisible({ timeout: 10000 });
    const colB2 = dialog2.locator('.kb-col', { hasText: catB }).first();
    await expect(colB2.locator('.wish-card')).toHaveCount(cardBoxCountBefore + 1, { timeout: 5000 });
    // «E2E temp column» не пережила закрытие — не сохранена нигде (ожидаемо).
    await expect(dialog2.locator('.kb-col', { hasText: 'E2E temp column' })).toHaveCount(0);

    await page.screenshot({
      path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/wish_kanban_04_reopened_persisted.png',
    });

    await page.keyboard.press('Escape');
  });

  test('Заявка approved — кнопка «Распределить» видна во «Все заявки» и «Мои»', async ({ page, request }) => {
    const headers = await authed(request, token);

    // wish_transitions.py::approve_wish конвертирует заявку С позициями СРАЗУ в
    // 'converted' (быстрое одобрение создаёт закупку не глядя), минуя 'approved'
    // — реалистичный устойчивый способ получить заявку именно в статусе
    // 'approved' (не converted) для теста видимости кнопки: заявка БЕЗ позиций
    // (`if wish.items:` в approve_wish — пусто, авто-конвертация не запускается).
    const createRes = await request.post(`${API_BASE}/wishes/`, {
      headers,
      data: { title: 'E2E approved-status distribute button (temp)' },
    });
    expect(createRes.ok()).toBeTruthy();
    const approvedWish = await createRes.json();
    const approvedWishId = approvedWish.id as number;
    const addApproverRes = await request.post(`${API_BASE}/wishes/${approvedWishId}/approvers`, {
      headers, data: { user_id: 1 },
    });
    expect(addApproverRes.ok()).toBeTruthy();
    const submitRes = await request.post(`${API_BASE}/wishes/${approvedWishId}/submit`, { headers });
    expect(submitRes.ok()).toBeTruthy();
    const approveRes = await request.post(`${API_BASE}/wishes/${approvedWishId}/approve`, { headers });
    expect(approveRes.ok()).toBeTruthy();
    const approvedBody = await approveRes.json();
    expect(approvedBody.status).toBe('approved');

    try {
      await login(page);
      await dismissOrgPicker(page);

      // «Мои»
      await page.goto('/wishes');
      await page.waitForLoadState('networkidle');
      const myRow = page.locator('tr', { hasText: 'E2E approved-status distribute button' }).first();
      await expect(myRow.getByRole('button', { name: /^Распределить$/ })).toBeVisible({ timeout: 10000 });

      // «Все заявки»
      const allTab = page.getByRole('tab', { name: /Заявки сотрудников/i }).first();
      if (await allTab.count()) {
        await allTab.click();
        await page.waitForLoadState('networkidle');
        const allRow = page.locator('tr', { hasText: 'E2E approved-status distribute button' }).first();
        await expect(allRow.getByRole('button', { name: /^Распределить$/ })).toBeVisible({ timeout: 10000 });
        await page.screenshot({
          path: 'C:/Users/1/Documents/VAULT_for_LLM/Projects/VSKS_CRM/Artifacts/wish_kanban_05_approved_distribute_button.png',
        });
      }
    } finally {
      await request.delete(`${API_BASE}/wishes/${approvedWishId}`, { headers }).catch(() => {});
    }
  });
});
