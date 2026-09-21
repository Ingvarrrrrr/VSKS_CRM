// Согласование превышения плана над финансированием ФЭО/над вручную заданным
// планом и «итог закупки дороже плана» — вынесено из SubsidiesView.vue (волна
// 5c). Единственный источник этой логики (Правило №6); AlignBudgetDialog.vue/
// ExcessRejectDialog.vue и строки дерева (FeoTreeRow.vue) читают/вызывают через
// ctx, не дублируют.
//
// Module-level singleton (как useKpiDrilldown.ts).
import { computed, ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { refreshMyPendingApprovals } from '@/composables/useApprovalsBadge'
import { useToast, type ToastType } from '@/composables/useToast'
import type {
  ExcessCulprit, ExcessPlanItem, ExcessPlanItemPurchase, FeoNode, PlanExcessApprovalDto, PlanExcessStep,
  PlanTreeEntry, SubsidyTypeExcess, TypeExcessInfo, TypeExcessKind,
} from './types'
import { formatCurrency } from './format'

interface FeoTreeExcessCtx {
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  planExcessApprovals: Ref<Record<number, PlanExcessApprovalDto>>
  selectedId: Ref<number | null>
  refreshReqData: (catId?: number) => Promise<void>
}

// Раздел E (план ancient-prancing-music.md, 2026-09-21) — единственный источник
// порядка/русских подписей 4 видов превышения ПО ТИПУ на фронте (зеркалит
// backend/app/services/plan_excess_kinds.KIND_LABELS для этих 4 kind, но текст
// здесь — короткая форма для строки дерева/чипа, не форматированное сообщение
// 409/комментария approval). FeoTreeRow.vue и SubsidyKpiCards.vue (другой
// агент) читают ЭТОТ массив, не заводят копию (Правило №6).
export const TYPE_EXCESS_KIND_DEFS: { kind: TypeExcessKind; label: string }[] = [
  { kind: 'plan_over_feo_goods', label: 'план по товарам выше ФЭО по товарам' },
  { kind: 'plan_over_feo_services', label: 'план по услугам выше ФЭО по услугам' },
  { kind: 'fact_over_plan_goods', label: 'закупки по товарам выше плана по товарам' },
  { kind: 'fact_over_plan_services', label: 'закупки по услугам выше плана по услугам' },
]

// Ключ карты согласований/loading по виду+уровню превышения ПО ТИПУ — ОДНА
// функция для построения ключа И его чтения на фронте (FeoTreeRow.vue,
// SubsidyKpiCards.vue), уровень субсидии = categoryId null (см.
// app.services.plan_excess_kinds.LEVEL_SUBSIDY на бэкенде).
export function typeExcessKey(categoryId: number | null, kind: TypeExcessKind): string {
  return `${categoryId ?? 'subsidy'}:${kind}`
}

const NODE_EXCESS_FIELD: Record<TypeExcessKind, string> = {
  plan_over_feo_goods: 'excess_plan_over_feo_goods',
  plan_over_feo_services: 'excess_plan_over_feo_services',
  fact_over_plan_goods: 'excess_fact_over_plan_goods',
  fact_over_plan_services: 'excess_fact_over_plan_services',
}

let _api: ReturnType<typeof buildFeoTreeExcess> | null = null

// ctx необязателен НАЧИНАЯ СО ВТОРОГО вызова (задача владельца, раздел C,
// 2026-09-21): SubsidiesView.vue строит singleton первым (с полным ctx) —
// FeoTreeRow.vue/FeoLevel5Panel.vue/FeoTreeToolbar.vue и SubsidyKpiCards.vue
// (другой агент, вне ctx SubsidyDetailContext — см. докстринг в
// FeoLevel5Panel.vue про useFeoLevel5Api()) переиспользуют УЖЕ построенный
// singleton вызовом БЕЗ аргумента — тот же паттерн, что и useFeoLevel5Api().
export function useFeoTreeExcess(ctx?: FeoTreeExcessCtx) {
  if (!_api) {
    if (!ctx) throw new Error('useFeoTreeExcess() вызван до первого построения (нужен ctx) — проверьте порядок монтирования SubsidiesView.vue')
    _api = buildFeoTreeExcess(ctx)
  }
  return _api
}

function buildFeoTreeExcess(ctx: FeoTreeExcessCtx) {
  const { planTreeByCat, planExcessApprovals, selectedId, refreshReqData } = ctx

  const toast = useToast()
  function showSnack(text: string, color: ToastType = 'success') {
    toast.addToast(text, color)
  }

  const userRoleRaw = localStorage.getItem('user_role') || ''
  const isSaas = computed(() => ['superadmin', 'account_owner'].includes(userRoleRaw))
  const currentUserId = Number(localStorage.getItem('user_id') || '0')

  const excessRequestLoading = ref<number | null>(null)
  const excessDecideLoading = ref<number | null>(null)

  function excessFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean } | null {
    const t = planTreeByCat.value[node.id]
    const amount = Number(t?.excess_amount || 0)
    if (amount <= 0.005) return null
    return { amount, pending: !!t?.excess_pending, approved: !!t?.excess_approved }
  }

  function excessCulpritFor(node: FeoNode): ExcessCulprit | null {
    return planTreeByCat.value[node.id]?.excess_culprit ?? null
  }

  function excessCulpritText(node: FeoNode): string {
    const c = excessCulpritFor(node)
    if (!c) return ''
    const source = c.purchase_number != null
      ? `закупка № ${c.purchase_number}${c.item_name ? ` «${c.item_name}»` : ''}`
      : (c.item_name || 'плановое значение категории')
    const budget = node.budget != null ? formatCurrency(node.budget) : '—'
    // Владелец, Волна 1 п.13 (2026-09-13), дословно: «сумма 4 012 784,48 плюс
    // общая сумма 6 645 234,48 — почему тогда общая сумма именно 6 645 234,48,
    // а не 8 012 784,48». Причина — прежний текст называл cumulative_after
    // («после неё выбрано») без пояснения, что это НАКОПЛЕННЫЙ итог на момент
    // пересечения черты, а не добавочная величина, и не показывал, чем всё
    // кончилось — читатель складывал его с итоговым планом сам. Текст ниже
    // держится того же честного смысла, что и 409-предупреждение
    // (assert_no_unapproved_excess, feo_plan_excess.py): называет позицию
    // ПЕРВОЙ, а не единственной причиной, и завершает тем же итоговым планом/
    // превышением, что и в чипе рядом («превышение N — требуется
    // согласование», excessFor читает то же excess_amount узла).
    return `из-за чего: ${source} — первая позиция, из-за которой план по категории перевалил за ФЭО (не единственная причина всего превышения). До неё было выбрано ${formatCurrency(c.amount_before)}, она добавила ${formatCurrency(c.amount_at_crossing)} — накопленным итогом на тот момент стало ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}. Дальше план продолжил расти и дошёл до ${formatCurrency(c.total_plan_amount)} — итоговое превышение ${formatCurrency(c.total_excess)}`
  }

  function isExcessCulpritActual(node: FeoNode, actual: { purchase_id: number; item_name: string }): boolean {
    const c = excessCulpritFor(node)
    if (!c || c.purchase_id == null) return false
    return c.purchase_id === actual.purchase_id && (c.item_name || '') === (actual.item_name || '')
  }

  function excessCulpritChipTooltip(node: FeoNode): string {
    const c = excessCulpritFor(node)
    if (!c) return ''
    const budget = node.budget != null ? formatCurrency(node.budget) : '—'
    // Тот же честный смысл, что в excessCulpritText выше, но короче — для
    // всплывающей подсказки над чипом плановой позиции (FeoLevel5Panel.vue).
    return `Первая позиция за чертой ФЭО (не единственная причина превышения): добавила ${formatCurrency(c.amount_at_crossing)}, накопленным итогом стало ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}. Итоговый план ${formatCurrency(c.total_plan_amount)}, итоговое превышение ${formatCurrency(c.total_excess)}`
  }

  function excessFactFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean } | null {
    const t = planTreeByCat.value[node.id]
    const amount = Number(t?.excess_fact_over_plan || 0)
    if (amount <= 0.005) return null
    return { amount, pending: !!t?.excess_fact_pending, approved: !!t?.excess_fact_approved }
  }

  function excessPlanFor(node: FeoNode): { amount: number; pending: boolean; approved: boolean; manualEntered: number; items: ExcessPlanItem[] } | null {
    const t = planTreeByCat.value[node.id]
    const amount = Number(t?.excess_plan_over_manual || 0)
    if (amount <= 0.005) return null
    return {
      amount,
      pending: !!t?.excess_plan_pending,
      approved: !!t?.excess_plan_approved,
      manualEntered: Number(t?.manual_plan_entered || 0),
      items: t?.excess_plan_items || [],
    }
  }

  function excessPlanItemPurchaseTitle(p: ExcessPlanItemPurchase): string {
    const num = p.registry_number || (p.purchase_number != null ? `№ ${p.purchase_number}` : `#${p.id}`)
    const status = p.status_label || p.status || '—'
    return `${num} · ${status} · ${formatCurrency(p.amount)}`
  }

  function excessPlanApprovalPermanent(node: FeoNode): { amount: number; at: string; by: string; planBefore: number | null; planAfter: number | null } | null {
    const t = planTreeByCat.value[node.id]
    if (t?.excess_approval_amount == null) return null
    return {
      amount: Number(t.excess_approval_amount),
      at: t.excess_approval_at ? new Date(t.excess_approval_at).toLocaleDateString('ru-RU') : '',
      by: t.excess_approval_by_name || '—',
      planBefore: t.excess_approval_plan_before != null ? Number(t.excess_approval_plan_before) : null,
      planAfter: t.excess_approval_plan_after != null ? Number(t.excess_approval_plan_after) : null,
    }
  }

  function excessApprovalFor(node: FeoNode): PlanExcessApprovalDto | null {
    return planExcessApprovals.value[node.id] || null
  }

  // ── Хелперы НАД approval-объектом напрямую (не над node) — общий низ для
  // старых per-node функций (excessPendingNames и т.п., по node.id) И новых
  // per-(category,kind) функций превышения по типу ниже (typeExcessPendingNames
  // и т.п.) — ПРАВИЛО №6, второй копии текста/поиска шага нет.
  function pendingNamesForApproval(appr: PlanExcessApprovalDto | null): string {
    if (!appr || appr.status !== 'pending') return ''
    const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
    const pendingSteps = appr.mode === 'parallel'
      ? sorted.filter(s => s.status === 'pending')
      : sorted.filter(s => s.status === 'pending').slice(0, 1)
    return pendingSteps.map(s => s.full_name || s.role_name || `пользователь #${s.user_id}`).join(', ')
  }

  function myPendingStepForApproval(appr: PlanExcessApprovalDto | null): PlanExcessStep | null {
    if (!appr || appr.status !== 'pending') return null
    const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
    if (appr.mode === 'parallel') {
      return sorted.find(s => s.status === 'pending' && (s.user_id === currentUserId || isSaas.value)) || null
    }
    const first = sorted.find(s => s.status === 'pending')
    if (first && (first.user_id === currentUserId || isSaas.value)) return first
    return null
  }

  function resolvedByNameForApproval(appr: PlanExcessApprovalDto | null): string {
    if (!appr) return ''
    const decided = [...appr.steps]
      .filter(s => s.status === 'approved' && s.decided_at)
      .sort((a, b) => new Date(b.decided_at!).getTime() - new Date(a.decided_at!).getTime())
    return decided[0]?.full_name || decided[0]?.role_name || '—'
  }

  function resolvedDateForApproval(appr: PlanExcessApprovalDto | null): string {
    if (!appr?.resolved_at) return ''
    return new Date(appr.resolved_at).toLocaleDateString('ru-RU')
  }

  // decide НАД approval id/step id напрямую — общая точка вызова POST
  // /plan-excess/{id}/decide для decidePlanExcess (старые 3 вида, по node) И
  // decideTypeExcess (новые 4 вида, по category+kind) ниже.
  async function postDecide(approvalId: number, stepId: number, decision: 'approved' | 'rejected', comment?: string) {
    await apiFetch(`/plan-excess/${approvalId}/decide`, {
      method: 'POST',
      body: JSON.stringify({ decision, step_id: stepId, comment: comment || null }),
    })
    showSnack(decision === 'approved' ? 'Превышение согласовано' : 'Превышение отклонено', decision === 'approved' ? 'success' : 'warning')
    if (selectedId.value) await refreshReqData()
    refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
  }

  function excessPendingNames(node: FeoNode): string {
    return pendingNamesForApproval(excessApprovalFor(node))
  }

  function excessMyPendingStep(node: FeoNode) {
    return myPendingStepForApproval(excessApprovalFor(node))
  }

  function excessResolvedByName(node: FeoNode): string {
    return resolvedByNameForApproval(excessApprovalFor(node))
  }

  function excessResolvedDate(node: FeoNode): string {
    return resolvedDateForApproval(excessApprovalFor(node))
  }

  // ── Раздел E (план ancient-prancing-music.md, 2026-09-21): карта согласований
  // ПО ВИДУ+УРОВНЮ превышения — ключ typeExcessKey(categoryId, kind), НЕ node.id
  // (в отличие от planExcessApprovals выше, который держит «первую по
  // категории», старая логика гашения ВСЕХ старых трёх видов одной записью).
  // Заполняется ТЕМ ЖЕ GET /plan-excess?subsidy_id= (список отдаёт ВСЕ kind —
  // старые и новые 4, category и subsidy уровень разом), см. loadPlanExcessApprovals.
  const typeExcessApprovals = ref<Record<string, PlanExcessApprovalDto>>({})
  const typeExcessRequestLoading = ref<string | null>(null)
  const typeExcessDecideLoading = ref<string | null>(null)

  function typeExcessApprovalFor(categoryId: number | null, kind: TypeExcessKind): PlanExcessApprovalDto | null {
    return typeExcessApprovals.value[typeExcessKey(categoryId, kind)] || null
  }

  function typeExcessPendingNames(categoryId: number | null, kind: TypeExcessKind): string {
    return pendingNamesForApproval(typeExcessApprovalFor(categoryId, kind))
  }

  function typeExcessMyPendingStep(categoryId: number | null, kind: TypeExcessKind) {
    return myPendingStepForApproval(typeExcessApprovalFor(categoryId, kind))
  }

  function typeExcessResolvedByName(categoryId: number | null, kind: TypeExcessKind): string {
    return resolvedByNameForApproval(typeExcessApprovalFor(categoryId, kind))
  }

  function typeExcessResolvedDate(categoryId: number | null, kind: TypeExcessKind): string {
    return resolvedDateForApproval(typeExcessApprovalFor(categoryId, kind))
  }

  // node=null — уровень субсидии целиком: суммы читаются из
  // planTreeByCat.value['subsidy_type_excess'] (см. докстринг SubsidyTypeExcess
  // в types.ts — этот же planTreeByCat, useFeoTreeState.ts::splitPlanTree не
  // фильтрует этот строковый ключ, второго state под него не заводим).
  function typeExcessFor(node: FeoNode | null, kind: TypeExcessKind): TypeExcessInfo | null {
    const categoryId = node ? node.id : null
    let amount = 0
    let pending = false
    let approved = false
    if (node) {
      const t = planTreeByCat.value[node.id] as any
      const field = NODE_EXCESS_FIELD[kind]
      amount = Number(t?.[field] || 0)
      pending = !!t?.[`${field}_pending`]
      approved = !!t?.[`${field}_approved`]
    } else {
      const summary = (planTreeByCat.value as any)?.['subsidy_type_excess'] as SubsidyTypeExcess | undefined
      const entry = summary?.[kind]
      amount = Number(entry?.amount || 0)
      pending = !!entry?.pending
      approved = !!entry?.approved
    }
    if (amount <= 0.005) return null
    return { amount, pending, approved, approval: typeExcessApprovalFor(categoryId, kind) }
  }

  async function loadPlanExcessApprovals(subsidyId: number) {
    try {
      const rows = await apiFetch<PlanExcessApprovalDto[]>(`/plan-excess?subsidy_id=${subsidyId}`)
      const map: Record<number, PlanExcessApprovalDto> = {}
      const typeMap: Record<string, PlanExcessApprovalDto> = {}
      for (const r of rows) {
        // planExcessApprovals (старые 3 вида, category-only) — первая по
        // категории, независимо от kind (прежнее поведение не меняем).
        if (r.feo_category_id != null && !(r.feo_category_id in map)) map[r.feo_category_id] = r
        // typeExcessApprovals — по ключу (categoryId|subsidy):kind, первая
        // (список уже отсортирован created_at DESC на бэкенде — самая свежая).
        if (r.kind) {
          const k = typeExcessKey(r.feo_category_id, r.kind as TypeExcessKind)
          if (!(k in typeMap)) typeMap[k] = r
        }
      }
      planExcessApprovals.value = map
      typeExcessApprovals.value = typeMap
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось загрузить согласования превышения плана', 'error')
    }
  }

  async function requestPlanExcessApproval(node: FeoNode) {
    excessRequestLoading.value = node.id
    try {
      const res = await apiFetch<PlanExcessApprovalDto>('/plan-excess', {
        method: 'POST',
        body: JSON.stringify({ feo_category_id: node.id }),
      })
      if (res.self_approval && res.warning) {
        showSnack(res.warning, 'warning')
      } else if (res.warning) {
        showSnack(`Запрос отправлен. ${res.warning}`, 'warning')
      } else {
        showSnack('Запрос на согласование превышения плана отправлен', 'success')
      }
      if (selectedId.value) await refreshReqData()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось запросить согласование превышения', 'error')
    } finally {
      excessRequestLoading.value = null
    }
  }

  async function decidePlanExcess(node: FeoNode, decision: 'approved' | 'rejected', comment?: string) {
    const appr = excessApprovalFor(node)
    const step = excessMyPendingStep(node)
    if (!appr || !step) {
      showSnack('Шаг согласования не найден — обновите страницу', 'error')
      return
    }
    excessDecideLoading.value = node.id
    try {
      await postDecide(appr.id, step.id, decision, comment)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
    } finally {
      excessDecideLoading.value = null
    }
  }

  // requestTypeExcessApproval/decideTypeExcess — раздел E (владелец, 21.09.2026):
  // те же вызовы API, что и requestPlanExcessApproval/decidePlanExcess выше
  // (POST /plan-excess, POST /plan-excess/{id}/decide — postDecide общий), с
  // добавленным body.kind и feo_category_id=null для уровня субсидии.
  //
  // ⚠️ ИЗВЕСТНЫЙ РАЗРЫВ КОНТРАКТА (проверено по коду бэкенда на момент
  // написания, 2026-09-21): backend/app/routers/plan_excess.py::
  // request_plan_excess_approval ТРЕБУЕТ truthy feo_category_id (422 «обязателен»
  // на null — уровень субсидии) И принимает kind ТОЛЬКО из старых трёх
  // (PEK.OVER_FEO/FACT_OVER_PLAN/PLAN_OVER_MANUAL — см. _kind_amounts в файле);
  // 4 новых kind (PLAN_OVER_FEO_GOODS и т.п.) регистрируются автоматически
  // backend/app/services/type_excess_approval.py::register_type_excess_approvals
  // (мягко — purchases.py create/PUT, wish_convert.py) и блокируются жёстко
  // purchase_transitions.py — ручного POST-триггера для НИХ на бэкенде нет.
  // Эта функция вызывает эндпоинт как задокументировано в задании (на случай,
  // если бэкенд её уже поддерживает или будет дополнен) — при 400/422 ошибка
  // не глотается, а показывается пользователю тем же catch, что и везде (см.
  // Lessons.md «не глотать ошибки generic-снэкбаром»). Для типового сценария
  // (превышение уже видно в дереве) approval обычно УЖЕ существует через
  // авторегистрацию — кнопка нужна как fallback, а не основной путь.
  async function requestTypeExcessApproval(node: FeoNode | null, kind: TypeExcessKind) {
    const categoryId = node ? node.id : null
    const key = typeExcessKey(categoryId, kind)
    typeExcessRequestLoading.value = key
    try {
      const res = await apiFetch<PlanExcessApprovalDto>('/plan-excess', {
        method: 'POST',
        body: JSON.stringify({ feo_category_id: categoryId, subsidy_id: node ? undefined : selectedId.value, kind }),
      })
      if (res.self_approval && res.warning) {
        showSnack(res.warning, 'warning')
      } else if (res.warning) {
        showSnack(`Запрос отправлен. ${res.warning}`, 'warning')
      } else {
        showSnack('Запрос на согласование превышения по типу отправлен', 'success')
      }
      if (selectedId.value) await refreshReqData()
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось запросить согласование превышения по типу', 'error')
    } finally {
      typeExcessRequestLoading.value = null
    }
  }

  async function decideTypeExcess(categoryId: number | null, kind: TypeExcessKind, decision: 'approved' | 'rejected', comment?: string) {
    const appr = typeExcessApprovalFor(categoryId, kind)
    const step = typeExcessMyPendingStep(categoryId, kind)
    if (!appr || !step) {
      showSnack('Шаг согласования не найден — обновите страницу', 'error')
      return
    }
    const key = typeExcessKey(categoryId, kind)
    typeExcessDecideLoading.value = key
    try {
      await postDecide(appr.id, step.id, decision, comment)
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
    } finally {
      typeExcessDecideLoading.value = null
    }
  }

  return {
    isSaas, currentUserId, excessRequestLoading, excessDecideLoading,
    excessFor, excessCulpritFor, excessCulpritText, isExcessCulpritActual, excessCulpritChipTooltip,
    excessFactFor, excessPlanFor, excessPlanItemPurchaseTitle, excessPlanApprovalPermanent,
    excessApprovalFor, excessPendingNames, excessMyPendingStep, excessResolvedByName, excessResolvedDate,
    loadPlanExcessApprovals, requestPlanExcessApproval, decidePlanExcess,
    // Раздел E — превышение по типу (товары/услуги), см. докстринги выше.
    typeExcessKindDefs: TYPE_EXCESS_KIND_DEFS, typeExcessKey,
    typeExcessRequestLoading, typeExcessDecideLoading,
    typeExcessApprovalFor, typeExcessPendingNames, typeExcessMyPendingStep,
    typeExcessResolvedByName, typeExcessResolvedDate, typeExcessFor,
    requestTypeExcessApproval, decideTypeExcess,
  }
}
