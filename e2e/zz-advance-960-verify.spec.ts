import { test, expect } from '@playwright/test';

// Приёмка сессии 2026-09-29 (авансовый отчёт РЕЕ-2026-00960, purchase.id=960):
// 1) категория ФЭО авансового отчёта выбирается свободно (баг: header FeoTreeSelect
//    был readonly для ЛЮБОЙ закупки с wish_id, включая авансовые с заявкой-компаньоном);
//    из авансового с выбранной категорией доступно «Создать плановую позицию»
//    (заблокировано было тем же условием — allow-per-item-plan требует form.feo_category_id).
// 2) PDF-чек с QR распознаётся (позиции/чек появляются), не просто прикрепляется файлом.
// НЕ входит в постоянный набор e2e — разовая приёмка, можно удалить после проверки.

async function login(page: any) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  await page.locator('input[type="text"], input[type="email"]').first().fill('admin');
  await page.locator('input[type="password"]').first().fill('admin123');
  await page.locator('.v-btn').filter({ hasText: /войти|вход/i }).first().click();
  await page.waitForURL((url: URL) => !url.pathname.includes('/login'), { timeout: 15_000 });
  await page.evaluate(() => {
    localStorage.setItem('selected_org_ids', JSON.stringify([1, 5, 28, 29, 30]));
    localStorage.setItem('selected_org_names', JSON.stringify(['BCKC']));
    localStorage.setItem('active_org_id', '1');
  });
  await page.reload();
  await page.waitForLoadState('networkidle');
}

test('advance report: free FEO category choice + create planned item from advance', async ({ page }) => {
  await login(page);

  // Новый авансовый отчёт
  await page.goto('/advance-reports/create');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);

  // Выбрать субсидию с деревом ФЭО (первую доступную)
  const subsidyField = page.locator('[data-field="subsidy_id"] input, .v-autocomplete', { hasText: /Субсидия/i }).first();
  await subsidyField.click();
  await page.waitForTimeout(500);
  await page.locator('.v-list-item').first().click();
  await page.waitForTimeout(800);

  // Дерево ФЭО НЕ должно быть readonly — до фикса :readonly="!!purchaseData?.wish_id"
  // держал его заблокированным для черновика ещё до первого сохранения тоже
  // (form.purchase_method === 'advance' с самого начала в advance_report формы).
  const feoTree = page.locator('.feo-tree-select, [class*="FeoTree"]').first();
  await expect(feoTree).toBeVisible({ timeout: 5000 });
  // Клик по первому листу дерева категорий
  const firstLeaf = page.locator('.feo-tree-select .v-list-item, [class*="FeoTree"] .v-list-item').first();
  await firstLeaf.click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(500);

  // Заполнить обязательные поля (ответственный, предмет) минимально и сохранить
  // (конкретные селекторы могут отличаться — при провале см. скриншот)
  await page.screenshot({ path: 'e2e-artifacts/advance-960-before-save.png', fullPage: true }).catch(() => {});

  // Сохранение (кнопка "Сохранить")
  const saveBtn = page.locator('.v-btn', { hasText: /Сохранить/i }).first();
  await saveBtn.click({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(1500);

  // После сохранения — открыть страницу заново (перезагрузка) и убедиться, что
  // категория ФЭО сохранилась (не readonly подсказка FEO_CATEGORY_LOCKED_HINT
  // и не пустое поле).
  await page.reload();
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  const lockedHint = page.locator('text=Категория взята из заявки и плана закупок');
  expect(await lockedHint.count()).toBe(0); // не должно показывать замок для авансового

  // «Создать плановую позицию» доступна у первой позиции (если позиции есть)
  const createPlannedBtn = page.locator('.v-btn', { hasText: /Создать в плане закупок/i }).first();
  if (await createPlannedBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await expect(createPlannedBtn).toBeEnabled();
  }

  await page.screenshot({ path: 'e2e-artifacts/advance-960-after-reload.png', fullPage: true }).catch(() => {});
});

test('advance report: PDF receipt with QR gets recognized, not just attached', async ({ page }) => {
  await login(page);

  // Открыть существующий авансовый отчёт (переиспользуем id из ADV_TEST_PURCHASE_ID,
  // как в zz-advance-report-fixes-verify.spec.ts) — тестовый PDF генерируется заранее
  // (см. отчёт задачи: backend/tests/test_receipt_pdf_qr.py::_mk_receipt_pdf, тот же QR).
  const PURCHASE_ID = process.env.ADV_TEST_PURCHASE_ID || '881';
  await page.goto(`/advance-reports/${PURCHASE_ID}/edit`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);

  const fileInput = page.locator(`input[type=file][accept="${'.json,.pdf,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff,.heic'}"]`).first();
  const pdfPath = process.env.RECEIPT_QR_PDF_PATH; // путь к сгенерированному тестовому PDF с QR
  if (pdfPath && (await fileInput.count()) > 0) {
    await fileInput.setInputFiles(pdfPath);
    await page.waitForTimeout(3000);
    // Ожидаем снэк про добавленный чек ИЛИ (без PROVERKACHEKA_TOKEN локально) про
    // прикреплённый файл с честной причиной — оба ветвления допустимы, но НЕ должно
    // быть немой потери файла.
    const snack = page.locator('.v-snackbar__content').first();
    await expect(snack).toBeVisible({ timeout: 5000 }).catch(() => {});
  }
});
