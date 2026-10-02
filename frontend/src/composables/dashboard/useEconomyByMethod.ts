// Квик-план 2026-10-02 («Деньги субсидии», PLAN.md п.4): «Статистика по
// способу закупки» — единственный источник данных (GET /dashboard/economy-by-
// method), фронт только грузит и суммирует там, где нужна строка «Итого»
// (Правило №6 — экономия/план/договор не пересчитываются, приходят готовыми
// по каждому способу закупки с бэкенда). Используется и дашбордом (без
// subsidy_id), и карточкой субсидии (с конкретным subsidy_id) — один и тот
// же composable, не копия.
import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'

export interface EconomyByMethodRow {
  method: string
  competitive_form: string | null
  label: string
  purchases: number
  // ИСПРАВЛЕНО 02.10.2026 (приёмка ФАДМ_2026 — null, когда у группы нет НИ
  // ОДНОЙ измеренной закупки; не форсить в 0, см. purchase_economy.py
  // docstring и EconomyByMethodTable.vue).
  plan: number | null
  fact: number | null
  economy: number | null
  economy_pct: number | null
  no_planned_price_items: number
  // ИСПРАВЛЕНО 02.10.2026 (дубль строки «Конкурентная»): true только для
  // строки-итога «Конкурентная — всего», когда у конкурентных закупок ≥ 2
  // разных значений competitive_form (см. purchase_economy.py
  // _format_method_group) — EconomyByMethodTable.vue выделяет её жирным.
  is_total?: boolean
  // ИСПРАВЛЕНО 02.10.2026 (база экономии — плановая позиция FeoPlannedItem):
  // разбивка no_planned_price_items по причине — показывать только ненулевые
  // (см. EconomyByMethodTable.vue).
  unmeasured_by_reason?: {
    unlinked: number
    no_plan_price: number
    monthly: number
    no_fact: number
  }
}

export function useEconomyByMethod(params?: { subsidyId?: Ref<number | null>; year?: Ref<number | null> }) {
  const rows = ref<EconomyByMethodRow[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  async function load() {
    loading.value = true
    try {
      const qs = new URLSearchParams()
      const subsidyId = params?.subsidyId?.value
      const year = params?.year?.value
      if (subsidyId != null) qs.set('subsidy_id', String(subsidyId))
      if (year != null) qs.set('year', String(year))
      const q = qs.toString()
      rows.value = await apiFetch<EconomyByMethodRow[]>(`/dashboard/economy-by-method${q ? '?' + q : ''}`)
      loaded.value = true
    } catch (e) {
      console.error('economy-by-method load error:', e)
      rows.value = []
    } finally {
      loading.value = false
    }
  }

  return { rows, loading, loaded, load }
}
