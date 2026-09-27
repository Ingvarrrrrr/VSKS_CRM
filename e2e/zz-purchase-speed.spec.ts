import { test, expect } from '@playwright/test';
import { login } from './helpers';

// Временный spec (владелец, 27.09.2026, «закупки грузятся долго, уже 10 секунд»):
// замер времени открытия карточки закупки ДО появления таблицы позиций +
// число/объём запросов /api/products при открытии. Сравнивается вручную
// ДО/ПОСЛЕ перф-правки (backend/app/routers/purchases.py,
// frontend/src/composables/items/useItemsCatalog.ts,
// frontend/src/views/CreateOrderView.vue) — сам файл не проверяет пороги,
// только печатает числа в отчёт теста.
test('открытие карточки закупки — время и запросы каталога товаров', async ({ page }) => {
  await login(page);

  const productsRequests: { url: string; sizeHint: number }[] = [];
  const allApi: string[] = [];
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/')) allApi.push(url);
    if (url.includes('/api/products')) {
      const len = Number(res.headers()['content-length'] || 0);
      productsRequests.push({ url, sizeHint: len });
    }
  });

  const t0 = Date.now();
  await page.goto('/orders/899');
  // Закупка 899 — «разные категории ФЭО для каждого товара» (ItemsTableStages,
  // не ItemsTableFlat) — ждём известную первую позицию по тексту, а не по
  // классу конкретной реализации таблицы (их несколько — Flat/Stages/Cards).
  await page.getByText('Кубок полуфинал', { exact: false }).first().waitFor({ timeout: 20_000 });
  const elapsed = Date.now() - t0;

  console.log(`[PERF] /orders/899: goto→первая строка позиций = ${elapsed} мс`);
  console.log(`[PERF] всего /api/* ответов: ${allApi.length}`);
  for (const u of allApi) console.log(`[PERF-API] ${u}`);
  console.log(`[PERF] запросов /api/products/*: ${productsRequests.length}`);
  for (const r of productsRequests) {
    console.log(`[PERF]   ${r.url} (content-length=${r.sizeHint})`);
  }
  const totalBytes = productsRequests.reduce((s, r) => s + r.sizeHint, 0);
  console.log(`[PERF] суммарно байт по /api/products/*: ${totalBytes}`);

  // Не качаем весь каталог (~4 МБ) при простом открытии карточки — только
  // узкие догрузки по id (обычно десятки-сотни байт на позицию).
  expect(totalBytes).toBeLessThan(500_000);
});
