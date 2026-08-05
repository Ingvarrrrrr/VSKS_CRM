// useFeoNodeAmounts — задача владельца (2026-08-06): «остаток средств напротив
// каждой категории ФЭО при выборе». Карта {feo_category_id: {budget, free}} для
// КАЖДОГО узла дерева (не только листа), источник — GET /feo-categories/plan-tree
// (per-node budget уже участвует в формуле display/excess_amount — см.
// app.services.feo_plan.compute_feo_plan_tree). free = budget − display — та же
// формула, что даёт «можно добавить / надо убрать» в дереве субсидий и KPI
// «Свободно» (SubsidiesView.vue), числа на экранах сойдутся.
//
// Право feo_budget.view_tree_amounts гейтит поля на бэкенде (budget/display приходят
// null без права) — здесь же не грузим запрос вообще без права, чтобы не тратить
// сеть на заведомо пустой ответ (authStore.hasAction, дефолт out of loadPermissions()
// на старте сессии).
//
// ⚠️ Перф: FeoTreeSelect рендерится в КАЖДОЙ строке таблицы позиций (до ~50 строк) и
// дерево бывает до ~400 категорий — карта считается ОДИН раз здесь (per subsidy_id),
// НЕ пересчитывается внутри FeoTreeSelect на каждый инстанс.
import { ref, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'

export interface FeoNodeAmount {
  /** Финансирование по ФЭО узла. */
  budget: number
  /** Свободный остаток = budget − display (плановая сумма узла). */
  free: number
}

export interface UseFeoNodeAmountsOptions {
  /** Subsidy whose ФЭО tree amounts we load (null → пусто). */
  subsidyId: Ref<number | null | undefined>
}

export function useFeoNodeAmounts(opts: UseFeoNodeAmountsOptions) {
  const nodeAmounts = ref<Record<number, FeoNodeAmount> | null>(null)
  const authStore = useAuthStore()

  watch(
    () => opts.subsidyId.value,
    async (subsidyId) => {
      if (!subsidyId || !authStore.hasAction('feo_budget.view_tree_amounts')) {
        nodeAmounts.value = null
        return
      }
      try {
        const tree = await apiFetch<Record<string, any>>(`/feo-categories/plan-tree?subsidy_id=${subsidyId}`)
        const map: Record<number, FeoNodeAmount> = {}
        for (const key of Object.keys(tree)) {
          if (key === 'unassigned') continue
          const node = tree[key]
          if (node == null || node.budget == null) continue
          const budget = Number(node.budget)
          const display = Number(node.display ?? 0)
          map[Number(key)] = { budget, free: budget - display }
        }
        nodeAmounts.value = map
      } catch {
        nodeAmounts.value = null
      }
    },
    { immediate: true },
  )

  return { nodeAmounts }
}
