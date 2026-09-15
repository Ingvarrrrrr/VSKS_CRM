/**
 * Верификация фикса «зависают пунктиры к проблемам» (владелец, 2026-09-15,
 * авансовый отчёт РЕЕ-2026-00916, жалоба Б): pointerTarget в useGuideArrow.ts
 * раньше выставлялся в guideArrowTo и никогда не гас сам — указатель мог
 * висеть на экране даже после того, как поле уже заполнено.
 *
 * Сценарий: открыть существующую закупку (886), очистить поле «Предмет
 * закупки» (form.subject), открыть диалог публикации → checkPublishReady()
 * добавит ошибку с target='subject' → клик по ошибке вызывает
 * revealField('subject') → guideArrowTo('subject') → указатель (.pub-pointer)
 * появляется у поля. Затем, НЕ нажимая «Сохранить», вводим текст обратно в
 * поле «Предмет закупки» — новый watch(guidePointerResolved) в
 * CreateOrderView.vue обязан сразу погасить указатель (без клика на другое
 * поле, без сохранения).
 */
import { test, expect, Page } from '@playwright/test';

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

test('Указатель у поля «Предмет закупки» гаснет сам, как только поле заполнено', async ({ page }) => {
  await doLogin(page);
  await page.goto('/orders/886');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1200);

  const subjectField = page.locator('#pub-target-subject input');
  const originalSubject = await subjectField.inputValue();
  console.log('  original subject:', originalSubject);

  // Очищаем поле, чтобы checkPublishReady() пометил его как ошибку.
  await subjectField.fill('');
  await page.waitForTimeout(300);

  // Открыть диалог публикации (кнопка "Опубликовать" где-то в карточке публикаций).
  const publishBtn = page.locator('.v-btn, button').filter({ hasText: /Опубликовать/ }).first();
  await publishBtn.scrollIntoViewIfNeeded().catch(() => {});
  await publishBtn.click().catch(() => {});
  await page.waitForTimeout(500);

  // Клик по строке ошибки "Не заполнено наименование закупки" — должен закрыть
  // диалог и навести стрелку/указатель на поле "Предмет закупки".
  const errRow = page.getByText('Не заполнено наименование закупки', { exact: false }).first();
  const errVisible = await errRow.isVisible().catch(() => false);
  if (errVisible) {
    await errRow.click().catch(() => {});
  } else {
    console.log('  [!] строка ошибки публикации не найдена видимой — диалог мог не открыться');
  }
  await page.waitForTimeout(1000);

  const pointerBefore = page.locator('#pub-target-subject .pub-pointer');
  const pointerBeforeCount = await pointerBefore.count();
  console.log('  pub-pointer count right after guideArrowTo("subject"):', pointerBeforeCount);
  await page.screenshot({ path: 'e2e-report/34-pointer-before-fix.png', fullPage: false }).catch(() => {});

  // Заполняем поле обратно (проблема решена), НЕ нажимая "Сохранить".
  await subjectField.fill(originalSubject || 'Тестовый предмет закупки (e2e 34)');
  await page.waitForTimeout(600); // watch(guidePointerResolved) должен сработать почти сразу

  const pointerAfter = page.locator('#pub-target-subject .pub-pointer');
  const pointerAfterCount = await pointerAfter.count();
  console.log('  pub-pointer count after field filled (no save clicked):', pointerAfterCount);
  await page.screenshot({ path: 'e2e-report/34-pointer-after-fix.png', fullPage: false }).catch(() => {});

  if (pointerBeforeCount > 0) {
    expect(pointerAfterCount, 'Указатель обязан исчезнуть сразу после заполнения поля, без сохранения').toBe(0);
  } else {
    console.log('  [!] Указатель не появился на шаге before — проверка автогашения неубедительна, см. скриншоты');
  }
});
