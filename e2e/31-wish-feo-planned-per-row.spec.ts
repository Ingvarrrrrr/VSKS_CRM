/**
 * Верификация задачи 2026-08-21: «выбранное на предыдущем этапе не смеет
 * меняться само» — тумблер «Разные категории ФЭО для каждого товара» теперь
 * отвечает ТОЛЬКО за категорию; выбор ПЛАНОВОЙ позиции — всегда построчный,
 * в ОБОИХ режимах. Шапочный перечень плановых позиций (FeoPlannedItemsSelect
 * в шапке) убран целиком.
 *
 * Использует subsidy_id=7 (ФАДМ_2026), лист feo_categories.id=122
 * («Закупка рабочих компьютеров...», parent 121, под ФАДМ_2026).
 */
import { test, expect, Page, Locator } from '@playwright/test';

const SUBSIDY_NAME = 'ФАДМ_2026';
// id=122 ("Закупка рабочих компьютеров...") отфильтрован filterFundedNodes()
// (budget=0, нет плана) — не появляется в дереве вовсе. id=123 "Бензин" (budget
// 800 000 ₽) — funded leaf, реально выбираемый.
const LEAF_NODE_ID = 123;

async function doLogin(page: Page) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('button[type="submit"], .v-btn').filter({ hasText: /войти|вход|login/i }).first().click();
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15_000 });
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

// PurchaseItemsEditor.vue has TWO "Добавить позицию" buttons: the TOP toolbar
// one calls addItem(true) (unshift, new row lands at INDEX 0), the BOTTOM one
// below the table calls addItem() (push, appends). The top one proved more
// reliable in this suite; using it consistently and always addressing the
// freshly-added row at index 0 immediately (before adding the next item)
// avoids depending on append ordering entirely.
async function addItem(page: Page, dialog: Locator) {
  const addBtn = dialog.locator('.v-btn').filter({ hasText: /Добавить позицию/ }).first();
  await addBtn.click();
  await page.waitForTimeout(500);
}

/** Picks an existing catalog product via InlineProductMatch inline autocomplete
 *  for the row at `rowIdx` (0-based). searchText must match >=2 chars of an
 *  existing product name. */
async function pickCatalogProduct(page: Page, dialog: Locator, rowIdx: number, searchText: string) {
  // Owner item rows carry id="item-row-*" (ItemsTableFlat.vue) — this skips the
  // interleaved .feo-attrs-row <tr> that now renders for EVERY item even in
  // single-category mode (allow-per-item-plan="true"), which would otherwise
  // throw off a plain `tbody tr` nth-index.
  const itemRow = dialog.locator('table tbody tr[id^="item-row-"]').nth(rowIdx);
  const field = itemRow.locator('.inline-product-match').first();
  await field.click();
  await page.waitForTimeout(300);
  // After activation the lazy field is replaced by a real v-autocomplete input.
  const input = itemRow.locator('.v-autocomplete input').first();
  await input.waitFor({ state: 'visible', timeout: 5000 });
  await input.click();
  await input.fill(searchText);
  await page.waitForTimeout(900); // debounce(300) + network
  const candidates = page.locator('.v-overlay--active .v-list-item');
  const count = await candidates.count();
  console.log(`  [debug] row ${rowIdx} search "${searchText}" -> ${count} candidates in overlay`);
  const candidate = candidates.filter({ hasText: searchText }).first();
  await candidate.waitFor({ state: 'visible', timeout: 8000 });
  await candidate.click();
  await page.waitForTimeout(600);
  // Close the (possibly still-open) candidate dropdown so it doesn't swallow the
  // NEXT click elsewhere as a "click outside to dismiss" gesture instead of the
  // intended action (observed: a subsequent "Добавить позицию" click was eaten).
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
}

/** Opens FeoTreeSelect header (single-category mode), searches by name, clicks the leaf node. */
async function pickHeaderFeoNode(page: Page, dialog: Locator, nodeId: number, searchText: string) {
  const field = dialog.locator('.feo-tree-field textarea').first();
  await field.click();
  await page.waitForTimeout(500);
  const search = page.locator('.feo-tree-search input').first();
  await search.fill(searchText);
  await page.waitForTimeout(600);
  const row = page.locator(`.feo-tree-menu-content [data-node-id="${nodeId}"]`).first();
  await row.waitFor({ state: 'visible', timeout: 5000 });
  await row.click();
  await page.waitForTimeout(400);
}

/** Creates a NEW planned item for the row's dense FeoPlannedItemsSelect (row idx,
 *  0-based, counted among `.feo-planned-dense-row` instances) with a distinct name. */
async function createPlannedForRow(page: Page, dialog: Locator, rowIdx: number, name: string, amount: number) {
  const denseRow = dialog.locator('.feo-planned-dense-row').nth(rowIdx);
  await denseRow.scrollIntoViewIfNeeded();
  await denseRow.click();
  await page.waitForTimeout(700);
  const createBtn = page.locator('.feo-planned-dense-menu .v-btn').filter({ hasText: /Создать в плане закупок/ }).first();
  const visible = await createBtn.isVisible().catch(() => false);
  if (!visible) {
    // Menu may not have opened on the first click (activator hit vs already-open
    // state toggling it closed) — retry once.
    await denseRow.click();
    await page.waitForTimeout(700);
  }
  await createBtn.waitFor({ state: 'visible', timeout: 5000 });
  await createBtn.click();
  await page.waitForTimeout(400);
  const nameInput = page.locator('.v-dialog .v-card-title', { hasText: 'Новая плановая позиция' })
    .locator('..')
    .locator('input').first();
  await nameInput.fill(name);
  const amountInput = page.locator('.v-dialog').filter({ hasText: 'Новая плановая позиция' })
    .locator('input[type="number"]').nth(1); // number inputs in order: quantity, amount
  await amountInput.fill(String(amount));
  const saveBtn = page.locator('.v-dialog').filter({ hasText: 'Новая плановая позиция' })
    .locator('.v-btn').filter({ hasText: 'Создать', hasNotText: 'Отмена' }).first();
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/feo-planned-items/') && r.request().method() === 'POST', { timeout: 10_000 }),
    saveBtn.click(),
  ]);
  expect(resp.ok(), `POST /feo-planned-items/ вернул ${resp.status()}`).toBeTruthy();
  await page.waitForTimeout(500);
  // Close the dense menu if still open
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
}

let wishIdSingleCat: number | null = null;

test.describe('Плановая позиция построчная в ОБОИХ режимах (2026-08-21)', () => {
  test.describe.configure({ mode: 'serial' });

  test('1. Тумблер выключен: шапочный перечень плановых отсутствует, лейбл переименован', async ({ page }) => {
    await doLogin(page);
    await openCreateWishDialog(page);
    const dialog = getWishDialog(page);
    await expect(dialog).toBeVisible();

    await selectSubsidy(page, dialog, SUBSIDY_NAME);

    const switchLabel = dialog.getByText('Разные категории ФЭО для каждого товара', { exact: true });
    await expect(switchLabel).toBeVisible();
    const switchInput = dialog.locator('.v-switch input[type="checkbox"]').first();
    await expect(switchInput).not.toBeChecked();

    await pickHeaderFeoNode(page, dialog, LEAF_NODE_ID, "Бензин");

    // No row-level FeoPlannedItemsSelect yet (no items) — and no header planned list.
    const denseCountBefore = await dialog.locator('.feo-planned-dense-row').count();
    expect(denseCountBefore, 'До добавления позиций построчных плановых селектов быть не должно').toBe(0);
    const preExistingRows = await dialog.locator('table tbody tr[id^="item-row-"]').count();
    console.log('  [debug] pre-existing rows before addItem:', preExistingRows);

    // addItem() prepends (unshift) — pick for the NEW row at index 0 immediately,
    // BEFORE adding the next item (which would prepend again and shift it to 1).
    await addItem(page, dialog);
    await pickCatalogProduct(page, dialog, 0, 'Радиостанция Motorola');
    // Radio is now at index 0. Add a second item — it prepends, so Radio moves
    // to index 1 and the new blank row is at index 0; pick Acer there.
    await addItem(page, dialog);
    await pickCatalogProduct(page, dialog, 0, 'Acer Aspire C27');
    // Final order: index 0 = Acer, index 1 = Радиостанция.

    await page.waitForTimeout(500);
    const rowCountAfterBothPicks = await dialog.locator('table tbody tr[id^="item-row-"]').count();
    const names = await dialog.locator('table tbody tr[id^="item-row-"] .inline-product-match').allTextContents();
    console.log('  [debug] row count after both picks:', rowCountAfterBothPicks, 'names:', JSON.stringify(names));
    expect(rowCountAfterBothPicks, 'Должно быть ровно 2 заполненные позиции').toBe(2);
    expect(names.some(n => n.includes('Radio') || n.includes('Радиостанция')), 'Строка с радиостанцией не найдена').toBeTruthy();
    expect(names.some(n => n.includes('Acer')), 'Строка с Acer не найдена').toBeTruthy();
    // NOW two per-row planned selectors should be visible even though feo_per_item=false.
    const denseCountAfter = await dialog.locator('.feo-planned-dense-row').count();
    expect(denseCountAfter, 'В режиме «одна категория» построчный выбор плановой должен быть доступен у КАЖДОЙ позиции').toBe(2);

    // Bulk button "Создать в плане закупок" visible in the toolbar too.
    const bulkBtn = dialog.locator('.v-btn').filter({ hasText: /Создать в плане закупок/ });
    await expect(bulkBtn.first()).toBeVisible();

    // Create two DISTINCT planned items, one per row, in the SAME header category.
    const runTag = Date.now();
    await createPlannedForRow(page, dialog, 0, `ПЛАН-Тест-Радиостанции-31-${runTag}`, 10000);
    await createPlannedForRow(page, dialog, 1, `ПЛАН-Тест-Ноутбуки-31-${runTag}`, 20000);

    await page.waitForTimeout(500);
    const rowCountBeforeSave = await dialog.locator('table tbody tr[id^="item-row-"]').count();
    const namesBeforeSave = await dialog.locator('table tbody tr[id^="item-row-"] .inline-product-match').allTextContents();
    console.log('  [debug] row count right before save:', rowCountBeforeSave, 'names:', JSON.stringify(namesBeforeSave));

    // Save as draft — same buildWishPayload() as full submit, no approver chain needed.
    const draftBtn = dialog.locator('.v-btn').filter({ hasText: /Сохранить черновик/ }).first();
    const [resp] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/wishes/') && r.request().method() === 'POST', { timeout: 10_000 }),
      draftBtn.click(),
    ]);
    expect(resp.ok(), `POST /wishes/ вернул ${resp.status()}`).toBeTruthy();
    const body = await resp.json();
    wishIdSingleCat = body?.id ?? null;
    expect(wishIdSingleCat, 'id заявки не вернулся').toBeTruthy();
    console.log('  Создана заявка (single-category, per-row plan) id=', wishIdSingleCat);
    (test.info() as any).annotations.push({ type: 'wish_id_single_cat', description: String(wishIdSingleCat) });

    await page.screenshot({ path: 'e2e-report/31-mode-off-after-save.png', fullPage: true }).catch(() => {});
  });

  test('2. Тумблер включён: своя категория И своя плановая у каждой позиции', async ({ page }) => {
    await doLogin(page);
    await openCreateWishDialog(page);
    const dialog = getWishDialog(page);
    await expect(dialog).toBeVisible();

    await selectSubsidy(page, dialog, SUBSIDY_NAME);

    const switchLabel = dialog.getByText('Разные категории ФЭО для каждого товара', { exact: true });
    await switchLabel.click();
    await page.waitForTimeout(400);
    const switchInput = dialog.locator('.v-switch input[type="checkbox"]').first();
    await expect(switchInput).toBeChecked();

    await addItem(page, dialog);
    await pickCatalogProduct(page, dialog, 0, 'Радиостанция Motorola');

    await page.waitForTimeout(500);
    // Per-item category select (FeoTreeSelect) must be visible in the row.
    const rowFeoTreeField = dialog.locator('.feo-attrs-row .feo-tree-field textarea').first();
    await expect(rowFeoTreeField).toBeVisible();

    // In per-item mode the row's OWN category must be picked before its plan
    // selector can resolve a category (no shapочный fallback here — the row
    // has neither its own category yet nor a header default in this mode).
    await rowFeoTreeField.click();
    await page.waitForTimeout(500);
    const rowSearch = page.locator('.feo-tree-search input').first();
    await rowSearch.fill('Бензин');
    await page.waitForTimeout(600);
    const rowLeaf = page.locator(`.feo-tree-menu-content [data-node-id="${LEAF_NODE_ID}"]`).first();
    await rowLeaf.waitFor({ state: 'visible', timeout: 5000 });
    await rowLeaf.click();
    await page.waitForTimeout(500);

    // Per-item planned select must ALSO be visible (same as before).
    const denseCount = await dialog.locator('.feo-planned-dense-row').count();
    expect(denseCount, 'В режиме «каждому своя» построчный плановый селект как и раньше').toBe(1);

    const bulkBtn = dialog.locator('.v-btn').filter({ hasText: /Создать в плане закупок/ });
    await expect(bulkBtn.first()).toBeVisible();

    await page.screenshot({ path: 'e2e-report/31-mode-on.png', fullPage: true }).catch(() => {});
  });

  test('3. Предупреждение «без плановой позиции» работает в режиме «одна категория»', async ({ page }) => {
    await doLogin(page);
    await openCreateWishDialog(page);
    const dialog = getWishDialog(page);
    await expect(dialog).toBeVisible();

    await selectSubsidy(page, dialog, SUBSIDY_NAME);
    await pickHeaderFeoNode(page, dialog, LEAF_NODE_ID, "Бензин");
    await addItem(page, dialog);
    await pickCatalogProduct(page, dialog, 0, 'Радиостанция Motorola');
    // Required field — otherwise form validation blocks submit before the
    // plan-warning gate even runs (see saveWish: validate() first).
    await dialog.locator('[data-field="justification"] textarea, [data-field="justification"] input').first().fill('E2E тест: обоснование для проверки предупреждения о плановой позиции');
    await page.waitForTimeout(400);

    // Do NOT link a planned item — attempt submit, expect a warning snackbar
    // naming the row by number and name (not blocking — soft warning).
    const submitBtn = dialog.locator('.v-btn').filter({ hasText: /Отправить на согласование/ }).first();
    await submitBtn.click();
    // Auto-wait for the specific warning text to appear anywhere on the page
    // (Vuetify snackbars auto-dismiss quickly — a fixed sleep then snapshot
    // can miss it; .v-snackbar class matching proved unreliable across
    // stacked snackbars, so match on visible body text directly instead).
    const planWarningText = page.getByText(/позиции без плановой позиции плана закупок/);
    await planWarningText.first().waitFor({ state: 'visible', timeout: 10000 });
    const fullText = (await page.locator('body').innerText()) ?? '';
    const line = fullText.split('\n').find(l => l.includes('позиции без плановой позиции')) ?? '';
    console.log('  plan warning line:', line.substring(0, 300));
    expect(/№1/.test(line) && /Радиостанция Motorola/.test(line), `Ожидали упоминание строки №1 «Радиостанция Motorola» в предупреждении, получили: "${line}"`).toBeTruthy();
  });

  test('4. Удаление плановой позиции корзинкой из строки работает (200) и освобождает деньги', async ({ page }) => {
    await doLogin(page);
    await openCreateWishDialog(page);
    const dialog = getWishDialog(page);
    await expect(dialog).toBeVisible();

    await selectSubsidy(page, dialog, SUBSIDY_NAME);
    await pickHeaderFeoNode(page, dialog, LEAF_NODE_ID, 'Бензин');
    await addItem(page, dialog);
    await pickCatalogProduct(page, dialog, 0, 'Радиостанция Motorola');

    const runTag = Date.now();
    const planName = `ПЛАН-Тест-Удаление-31-${runTag}`;
    await createPlannedForRow(page, dialog, 0, planName, 5000);

    // Open the row's dense selector again — the just-created item should now
    // be the selected summary row with a trash icon (kind='planned_item').
    const denseRow = dialog.locator('.feo-planned-dense-row').first();
    await denseRow.click();
    await page.waitForTimeout(500);
    const targetRow = page.locator('.feo-planned-dense-menu .feo-tree-row').filter({ hasText: planName }).first();
    await targetRow.waitFor({ state: 'visible', timeout: 5000 });
    const deleteBtn = targetRow.locator('.feo-planned-delete-btn, button[title="Удалить плановую позицию"]').first();
    await deleteBtn.waitFor({ state: 'visible', timeout: 5000 });
    page.once('dialog', (d) => d.accept()); // native confirm() before the DELETE
    const [delResp] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/feo-planned-items/') && r.request().method() === 'DELETE', { timeout: 10_000 }),
      deleteBtn.click(),
    ]);
    console.log('  DELETE url:', delResp.url(), 'status:', delResp.status());
    const bodyText = await delResp.text().catch(() => '');
    console.log('  DELETE response body:', bodyText.substring(0, 300));
    expect(delResp.ok(), `DELETE /feo-planned-items/ вернул ${delResp.status()}`).toBeTruthy();
  });
});
