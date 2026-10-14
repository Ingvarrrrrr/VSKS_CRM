// useAvgPrice.ts — подсказка «Средняя цена» у позиции заявки/закупки
// (план clever-bouncing-lantern.md, Часть 2, п.7). ОДИН экземпляр на весь
// редактор позиций (PurchaseItemsEditor.vue инстанцирует один раз и
// прокидывает avgPriceFor() вниз в ItemsTableStages/Flat/Wish/CardsView —
// ПРАВИЛО №6, второй таймер/вторая карта результатов в дочерних таблицах не
// заводится).
//
// Запросы идут ПАЧКОЙ: POST /api/products/avg-price/bulk принимает один
// org_id + одно quantity на весь список product_ids — группируем позиции по
// партии (см. utils/avgPrice.ts::batchLabelFromQuantity), один HTTP-запрос
// на каждую партию, встречающуюся в форме (не на каждую строку). Дебаунс —
// чтобы смена количества на каждый символ не долбила бэкенд.
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import { batchLabelFromQuantity, type AvgPriceStats } from '@/utils/avgPrice'

const DEBOUNCE_MS = 400

export interface AvgPriceLineInput {
  productId: number | null | undefined
  quantity: number | null | undefined
}

export function useAvgPrice() {
  // Ключ — product_id. Значение — последний посчитанный результат для него
  // (один и тот же товар в разных строках с разным кол-вом — редкий случай;
  // хватает последнего ответа, это подсказка, не источник истины расчётов).
  const results = reactive<Record<number, AvgPriceStats | null>>({})
  const loading = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let requestSeq = 0

  async function fetchGroup(productIds: number[], orgId: number | null | undefined, quantity: number | null) {
    if (!productIds.length) return
    try {
      const data = await apiFetch<Record<string, AvgPriceStats>>('/products/avg-price/bulk', {
        method: 'POST',
        body: { product_ids: productIds, org_id: orgId ?? null, quantity },
      })
      for (const [pid, stats] of Object.entries(data || {})) {
        results[Number(pid)] = stats
      }
    } catch {
      // Подсказка необязательная — тихо не показываем её, не мешаем вводу цены.
    }
  }

  async function runFetch(lines: AvgPriceLineInput[], orgId: number | null | undefined) {
    const mySeq = ++requestSeq
    const groups = new Map<string, { quantity: number | null; ids: Set<number> }>()
    for (const line of lines) {
      const pid = line.productId
      if (pid == null) continue
      const batch = batchLabelFromQuantity(line.quantity)
      const key = batch ?? '__none__'
      if (!groups.has(key)) groups.set(key, { quantity: line.quantity ?? null, ids: new Set() })
      groups.get(key)!.ids.add(pid)
    }
    if (!groups.size) return
    loading.value = true
    try {
      await Promise.all(
        [...groups.values()].map(g => fetchGroup([...g.ids], orgId, g.quantity)),
      )
    } finally {
      if (mySeq === requestSeq) loading.value = false
    }
  }

  /** Запланировать (с дебаунсом) пересчёт для текущего набора строк. Вызывать
   * при изменении состава позиций/количеств/организации. */
  function schedule(lines: AvgPriceLineInput[], orgId: number | null | undefined) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { runFetch(lines, orgId) }, DEBOUNCE_MS)
  }

  function statsFor(productId: number | null | undefined): AvgPriceStats | null {
    if (productId == null) return null
    return results[productId] ?? null
  }

  return { schedule, statsFor, loading }
}
