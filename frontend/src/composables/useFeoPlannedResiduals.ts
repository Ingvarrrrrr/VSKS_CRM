// useFeoPlannedResiduals — encapsulates loading «плановых позиций» субсидии из
// единого источника GET /feo-categories/plan-positions. Плановая позиция —
// конечный элемент дерева ФЭО (FeoCategory без детей) с заполненными
// planned_quantity/planned_amount ('plan_position' — плана без статьи ФЭО,
// 'feo_article' — план = статья ФЭО), ЛИБО отдельная запись FeoPlannedItem
// (Ур.5, необязательная детализация внутри элемента, 'planned_item').
//
// ⚠️ id-КОЛЛИЗИЯ: kind:'plan_position'/'feo_article' → id это id FeoCategory;
// kind:'planned_item' → id это id FeoPlannedItem. Это РАЗНЫЕ пространства id
// и они могут совпадать (одна и та же цифра — разные сущности). Поэтому
// сравнение/выбор конкретной строки ВСЕГДА идёт по составному `key`
// (`${kind}:${id}`), никогда по голому id.
import { computed, ref, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'

export type FeoPlanKind = 'plan_position' | 'feo_article' | 'planned_item'

/** Составной идентификатор строки — единственный безопасный ключ для сравнения/выбора. */
export interface FeoPlanSelection {
  kind: FeoPlanKind
  id: number
}

export interface FeoPlanPosition {
  /** id FeoCategory (kind='plan_position'|'feo_article') ИЛИ id FeoPlannedItem
   *  (kind='planned_item') — см. предупреждение о коллизии выше. Используйте `key`. */
  id: number
  name: string
  /** Путь по дереву ФЭО, напр. "Транспорт › Внедорожники › Great Wall POER". */
  path: string
  /** id FeoCategory, к которой относится строка (для planned_item — id родительского листа). */
  category_id: number
  kind: FeoPlanKind
  planned_quantity: number | null
  unit: string
  /** ИТОГОВАЯ сумма плана (planned_quantity × unit_price). */
  planned_amount: number | null
  /** Цена за единицу. */
  unit_price: number | null
  consumed: number
  consumed_quantity: number
  residual: number
  residual_quantity: number
  /** `${kind}:${id}` — безопасный составной ключ для выбора/сравнения строк. */
  key: string
}

/** @deprecated старое имя интерфейса (было завязано на /feo-planned-items/residuals) —
 *  оставлено алиасом на случай внешних импортов. Используйте {@link FeoPlanPosition}. */
export type FeoPlannedResidual = FeoPlanPosition

export interface UseFeoPlannedResidualsOptions {
  /** Subsidy whose plan positions we load (null → empty list). */
  subsidyId: Ref<number | null | undefined>
  /** Заявка, которую редактируем — исключить её собственную бронь остатка.
   *  ⚠️ Бэкенд /feo-categories/plan-positions пока НЕ поддерживает exclude_wish_id
   *  (параметр отправляется и молча игнорируется) — при редактировании заявки её
   *  собственная бронь по-прежнему учитывается в consumed/residual. */
  excludeWishId?: Ref<number | null | undefined>
}

export function useFeoPlannedResiduals(opts: UseFeoPlannedResidualsOptions) {
  const plannedResiduals = ref<FeoPlanPosition[]>([])
  const plannedLoading = ref(false)

  async function reloadPlanned() {
    const subsidyId = opts.subsidyId.value
    const excludeId = opts.excludeWishId?.value
    if (!subsidyId) {
      plannedResiduals.value = []
      return
    }
    plannedLoading.value = true
    try {
      const qs = excludeId != null ? `&exclude_wish_id=${excludeId}` : ''
      const rows = await apiFetch<Array<Omit<FeoPlanPosition, 'key'>>>(
        `/feo-categories/plan-positions?subsidy_id=${subsidyId}${qs}`
      )
      plannedResiduals.value = rows.map(r => ({ ...r, key: `${r.kind}:${r.id}` }))
    } catch {
      plannedResiduals.value = []
    } finally {
      plannedLoading.value = false
    }
  }

  watch(
    () => [opts.subsidyId.value, opts.excludeWishId?.value] as const,
    () => { reloadPlanned() },
    { immediate: true },
  )

  const plannedByCategory = computed((): Map<number, FeoPlanPosition[]> => {
    const map = new Map<number, FeoPlanPosition[]>()
    for (const row of plannedResiduals.value) {
      const arr = map.get(row.category_id) || []
      arr.push(row)
      map.set(row.category_id, arr)
    }
    return map
  })

  /** Найти строку по составному ключу (`${kind}:${id}`). */
  function getPlannedItem(key: string | null | undefined): FeoPlanPosition | null {
    if (!key) return null
    return plannedResiduals.value.find(r => r.key === key) ?? null
  }

  return { plannedResiduals, plannedByCategory, plannedLoading, getPlannedItem, reloadPlanned }
}
