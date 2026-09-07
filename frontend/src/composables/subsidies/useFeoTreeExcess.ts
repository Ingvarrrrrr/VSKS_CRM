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
import type { ExcessCulprit, ExcessPlanItem, ExcessPlanItemPurchase, FeoNode, PlanExcessApprovalDto, PlanTreeEntry } from './types'
import { formatCurrency } from './format'

interface FeoTreeExcessCtx {
  planTreeByCat: Ref<Record<number, PlanTreeEntry>>
  planExcessApprovals: Ref<Record<number, PlanExcessApprovalDto>>
  selectedId: Ref<number | null>
  refreshReqData: (catId?: number) => Promise<void>
}

let _api: ReturnType<typeof buildFeoTreeExcess> | null = null

export function useFeoTreeExcess(ctx: FeoTreeExcessCtx) {
  if (!_api) _api = buildFeoTreeExcess(ctx)
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
    return `из-за чего: ${source} — добавила ${formatCurrency(c.amount_at_crossing)}, после неё выбрано ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}`
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
    return `Добавила ${formatCurrency(c.amount_at_crossing)} — после неё выбрано ${formatCurrency(c.cumulative_after)} при ФЭО ${budget}`
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

  function excessPendingNames(node: FeoNode): string {
    const appr = excessApprovalFor(node)
    if (!appr || appr.status !== 'pending') return ''
    const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
    const pendingSteps = appr.mode === 'parallel'
      ? sorted.filter(s => s.status === 'pending')
      : sorted.filter(s => s.status === 'pending').slice(0, 1)
    return pendingSteps.map(s => s.full_name || s.role_name || `пользователь #${s.user_id}`).join(', ')
  }

  function excessMyPendingStep(node: FeoNode) {
    const appr = excessApprovalFor(node)
    if (!appr || appr.status !== 'pending') return null
    const sorted = [...appr.steps].sort((a, b) => a.order_num - b.order_num)
    if (appr.mode === 'parallel') {
      return sorted.find(s => s.status === 'pending' && (s.user_id === currentUserId || isSaas.value)) || null
    }
    const first = sorted.find(s => s.status === 'pending')
    if (first && (first.user_id === currentUserId || isSaas.value)) return first
    return null
  }

  function excessResolvedByName(node: FeoNode): string {
    const appr = excessApprovalFor(node)
    if (!appr) return ''
    const decided = [...appr.steps]
      .filter(s => s.status === 'approved' && s.decided_at)
      .sort((a, b) => new Date(b.decided_at!).getTime() - new Date(a.decided_at!).getTime())
    return decided[0]?.full_name || decided[0]?.role_name || '—'
  }

  function excessResolvedDate(node: FeoNode): string {
    const appr = excessApprovalFor(node)
    if (!appr?.resolved_at) return ''
    return new Date(appr.resolved_at).toLocaleDateString('ru-RU')
  }

  async function loadPlanExcessApprovals(subsidyId: number) {
    try {
      const rows = await apiFetch<PlanExcessApprovalDto[]>(`/plan-excess?subsidy_id=${subsidyId}`)
      const map: Record<number, PlanExcessApprovalDto> = {}
      for (const r of rows) {
        if (!(r.feo_category_id in map)) map[r.feo_category_id] = r
      }
      planExcessApprovals.value = map
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
      await apiFetch(`/plan-excess/${appr.id}/decide`, {
        method: 'POST',
        body: JSON.stringify({ decision, step_id: step.id, comment: comment || null }),
      })
      showSnack(decision === 'approved' ? 'Превышение согласовано' : 'Превышение отклонено', decision === 'approved' ? 'success' : 'warning')
      if (selectedId.value) await refreshReqData()
      refreshMyPendingApprovals()  // бейдж «мои согласования» в сайдбаре
    } catch (e: any) {
      showSnack(e?.payload?.message || e?.message || 'Не удалось сохранить решение', 'error')
    } finally {
      excessDecideLoading.value = null
    }
  }

  return {
    isSaas, currentUserId, excessRequestLoading, excessDecideLoading,
    excessFor, excessCulpritFor, excessCulpritText, isExcessCulpritActual, excessCulpritChipTooltip,
    excessFactFor, excessPlanFor, excessPlanItemPurchaseTitle, excessPlanApprovalPermanent,
    excessApprovalFor, excessPendingNames, excessMyPendingStep, excessResolvedByName, excessResolvedDate,
    loadPlanExcessApprovals, requestPlanExcessApproval, decidePlanExcess,
  }
}
