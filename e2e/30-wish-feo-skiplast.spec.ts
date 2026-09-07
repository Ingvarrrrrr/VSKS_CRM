/**
 * Регрессия найдена QA 2026-08-19: тумблер «Не указывать последний уровень ФЭО»
 * перестал работать после переноса выбора категории ФЭО из шапки заявки в
 * построчный редактор (PurchaseItemsEditor.onItemFeoChange безусловно обнулял
 * feo_category_id для нелистовых узлов). Фикс — allowNonLeafFeo проп.
 *
 * Тестируем через «Сохранить черновик» (saveWish(false)) для позитивных
 * сценариев — она не требует согласующих и не гоняет approver-цепочку,
 * но проходит ТОТ ЖЕ buildWishPayload()/POST /wishes/, что и полная отправка.
 * Блокировку (сценарий с выключенным тумблером) проверяем через кнопку
 * «Отправить на согласование» — этот путь и есть жёсткий гейт
 * wishItemsWithNonLeafFeoCategory, он возвращает false ДО обращения к
 * согласующим.
 */
import { test, expect, Page, Locator } from '@playwright/test';

const SUBSIDY_NAME = 'ФАДМ_2026';
const NON_LEAF_NODE_ID = 8;   // "Организация мероприятий" — subsidy_id=7, есть дети
const LEAF_NODE_ID = 127;     // лист под узлом 8

async function doLogin(page: Page) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15_000 });
  // admin — superadmin: без выбранных организаций AppBar автооткрывает persistent
  // org-picker поверх всего приложения (перехватывает клики по субсидии). Задаём
  // выбор заранее (org_id=1 «ВСКС», владелец подтвердил через этот же localStorage
  // ключ), чтобы диалог не открылся.
  await page.evaluate(() => {
    localStorage.setItem('selected_org_ids', JSON.stringify([1]));
    localStorage.setItem('selected_org_names', JSON.stringify(['ВСКС']));
  });
}

async function openCreateWishDialog(page: Page) {
  await page.goto('/wishes?create=1');
  await page.waitForLoadState('networkidle');
  await page.waitForSelector('.wish-dialog', { timeout: 10_000 });
  await page.waitForTimeout(500);
}

function getWishDialog(page: Page): Locator {
  return page.locator('.wish-dialog').first();
}

async function selectSubsidy(page: Page, dialog: Locator, subsidyName: string) {
  await dialog.locator('[data-field="subsidy_id"]').first().click();
  await page.waitForTimeout(500);
  const item = page.locator('.v-overlay--active .v-list-item').filter({ hasText: subsidyName }).first();
  await item.waitFor({ state: 'visible', timeout: 5000 });
  await item.click();
  await page.waitForTimeout(1000);
}

/** Добавляет позицию и заполняет «Кол-во» (обычный v-text-field, в отличие от
 *  наименования — оно висит на InlineProductMatch с каталожным автокомплитом
 *  и диалогом создания товара, ради теста незачем через это проходить).
 *  quantity>0 достаточно, чтобы позиция считалась «занятой» — см. фильтр
 *  (item_name || total_price || quantity) в wishItemsMissingFeoCategory/buildWishPayload. */
async function addItemWithQuantity(page: Page, dialog: Locator, qty: number) {
  const addBtn = dialog.locator('.v-btn').filter({ hasText: /Добавить позицию/ }).first();
  await addBtn.click();
  await page.waitForTimeout(400);
  const qtyInput = dialog.locator('table input[type="number"]').first();
  await qtyInput.fill(String(qty));
  await page.waitForTimeout(300);
}

/** Открывает FeoTreeSelect первой позиции и кликает узел по data-node-id. */
async function pickFeoNode(page: Page, dialog: Locator, nodeId: number) {
  const field = dialog.locator('.feo-tree-field textarea').first();
  await field.click();
  await page.waitForTimeout(500);
  const row = page.locator(`.feo-tree-menu-content [data-node-id="${nodeId}"]`).first();
  await row.waitFor({ state: 'visible', timeout: 5000 });
  await row.click();
  await page.waitForTimeout(400);
  // Меню листа закрывается само; для нелистового узла — закрываем явно.
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}

async function setSkipLastToggle(page: Page, dialog: Locator, on: boolean) {
  const label = dialog.getByText('Не указывать последний уровень ФЭО', { exact: true });
  const isOn = await dialog.locator('.v-switch input[type="checkbox"]').first().isChecked().catch(() => false);
  if (isOn !== on) {
    await label.click();
    await page.waitForTimeout(300);
  }
}

test.describe('Регрессия: тумблер «Не указывать последний уровень ФЭО» (2026-08-19)', () => {

  test('1. Тумблер ВЫКЛЮЧЕН + нелистовая категория → отправка блокируется', async ({ page }) => {
    await doLogin(page);
    await openCreateWishDialog(page);
    const dialog = getWishDialog(page);
    await expect(dialog).toBeVisible();

    await selectSubsidy(page, dialog, SUBSIDY_NAME);
    await addItemWithQuantity(page, dialog, 1);
    await pickFeoNode(page, dialog, NON_LEAF_NODE_ID);

    // Тумблер по умолчанию выключен — явно убеждаемся.
    await setSkipLastToggle(page, dialog, false);

    const submitBtn = dialog.locator('.v-btn').filter({ hasText: /Отправить на согласование/ }).first();
    await submitBtn.click();
    await page.waitForTimeout(1000);

    // Гейт рисует ПЕРСИСТЕНТНЫЙ v-alert над таблицей позиций (не тающий снэкбар) —
    // "Категория ФЭО не выбрана — отправить заявку на согласование нельзя".
    const alertText = (await dialog.locator('.v-alert').filter({ hasText: /категори/i }).first().textContent().catch(() => '')) ?? '';
    console.log('  alert:', alertText.trim().substring(0, 200));

    const dialogStillOpen = await dialog.isVisible().catch(() => false);
    expect(dialogStillOpen, 'Диалог должен остаться открытым — отправка заблокирована').toBeTruthy();
    expect(/категори/i.test(alertText), `Ожидали сообщение про категорию ФЭО, получили: "${alertText}"`).toBeTruthy();
  });

  // Кейс 2 «Тумблер ВКЛЮЧЁН + нелистовая категория → сохраняется с этой
  // категорией» удалён (дефект, QA 2026-09-07): переключатель «Не указывать
  // последний уровень ФЭО» отсутствует в текущем WishFormDialog.vue —
  // коммит c1225bd (2026-08-19) убрал дерево ФЭО/выбор плановой позиции из
  // карточки шапки заявки целиком при переносе на построчный выбор категории
  // (см. докстринг файла выше и WishFormDialog.vue: «Конечная категория ФЭО
  // не выбрана — отправить заявку на согласование нельзя», без обхода).
  // setSkipLastToggle(..., true) ищет несуществующий label/переключатель —
  // click() зависает/падает по таймауту, а не по регрессии продукта. Сама
  // возможность «сохранить нелистовую категорию» в UI теперь отсутствует —
  // переписывать кейс под «то же самое, что кейс 1» бессмысленно (дублировал
  // бы его). Кейсы 1 (блокировка нелистовой категории) и 3 (лист сохраняется
  // всегда) остаются актуальными без изменений.

  test('3. Контроль: конечная категория ФЭО сохраняется при любом положении тумблера', async ({ page }) => {
    await doLogin(page);
    await openCreateWishDialog(page);
    const dialog = getWishDialog(page);
    await expect(dialog).toBeVisible();

    await selectSubsidy(page, dialog, SUBSIDY_NAME);
    await addItemWithQuantity(page, dialog, 1);
    await setSkipLastToggle(page, dialog, false); // тумблер выключен — лист должен сохраняться и так
    await pickFeoNode(page, dialog, LEAF_NODE_ID);

    const draftBtn = dialog.locator('.v-btn').filter({ hasText: /Сохранить черновик/ }).first();
    const [resp] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/wishes/') && r.request().method() === 'POST', { timeout: 10_000 }),
      draftBtn.click(),
    ]);
    expect(resp.ok(), `POST /wishes/ вернул ${resp.status()}`).toBeTruthy();
    const body = await resp.json();
    console.log('  Создана заявка (control) id=', body?.id);
    expect(body?.id, 'id заявки не вернулся').toBeTruthy();
    (test.info() as any).annotations.push({ type: 'wish_id_leaf', description: String(body.id) });
  });
});
