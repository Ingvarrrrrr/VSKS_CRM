// Окно расшифровки суммы строки дерева ФЭО («В закупках» / «законтрактовано» /
// «из них заказано» / «зарезервировано» / «не распределено») — клик по любому
// из этих чисел открывает список закупок ПОДДЕРЕВА категории (решение
// владельца 06.10.2026, .planning/quick/2026-10-06-feo-row-sums/PLAN.md, шаг
// 4). GET /feo-categories/{id}/row-drill?subsidy_id=N&kind=... уже считает по
// поддереву на бэке — фронт ничего не суммирует, только показывает готовые
// строки и total (Правило №6, та же схема, что ContractsDrillDialog.vue).
//
// Module-level singleton БЕЗ ctx (как useFeoTreePrefs.ts) — своё состояние
// (visible/loading/rows), ничего не читает из SubsidyDetailContext. Открывает
// FeoTreeRow.vue (много экземпляров строк дерева), диалог-вёрстка
// (FeoRowDrillDialog.vue) смонтирован ОДИН раз в FeoTreeTable.vue и просто
// читает этот же объект — тот же приём, что useExcessDrilldown()/
// ExcessDrilldownBar.vue.
import { ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'

export type FeoRowDrillKind = 'in_purchases' | 'contracted' | 'ordered' | 'reserved' | 'unallocated'

export interface FeoRowDrillRow {
  purchase_id: number
  registry_number: string | number | null
  contractor: string | null
  reimbursement_user: string | null
  contract_type: string | null
  status: string | null
  subject: string | null
  feo_category_id: number | null
  feo_category_name: string | null
  amount: number
}

// Подписи окна по виду строки — одна карта, читают и FeoTreeRow.vue (что
// открывать по клику), и FeoRowDrillDialog.vue (заголовок окна).
export const FEO_ROW_DRILL_LABELS: Record<FeoRowDrillKind, string> = {
  in_purchases: 'В закупках',
  contracted: 'Законтрактовано',
  ordered: 'Из них заказано',
  reserved: 'Зарезервировано на ежемесячные',
  unallocated: 'Не распределено по договорам',
}

function buildFeoRowDrill() {
  const visible = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const rows = ref<FeoRowDrillRow[]>([])
  const total = ref(0)
  const kind = ref<FeoRowDrillKind>('in_purchases')
  const categoryId = ref<number | null>(null)
  const categoryName = ref('')

  async function open(categoryIdArg: number, categoryNameArg: string, subsidyId: number, kindArg: FeoRowDrillKind) {
    visible.value = true
    loading.value = true
    error.value = null
    rows.value = []
    total.value = 0
    kind.value = kindArg
    categoryId.value = categoryIdArg
    categoryName.value = categoryNameArg
    try {
      const res = await apiFetch<{ rows: FeoRowDrillRow[]; total: number }>(
        `/feo-categories/${categoryIdArg}/row-drill?subsidy_id=${subsidyId}&kind=${kindArg}`,
      )
      rows.value = res.rows || []
      total.value = res.total || 0
    } catch (e: any) {
      error.value = describeApiError(e, { fallback: 'Не удалось загрузить список закупок' })
    } finally {
      loading.value = false
    }
  }

  function close() {
    visible.value = false
  }

  return { visible, loading, error, rows, total, kind, categoryId, categoryName, open, close }
}

let api: ReturnType<typeof buildFeoRowDrill> | null = null
export function useFeoRowDrill() {
  if (!api) api = buildFeoRowDrill()
  return api
}
