// Экран ПРОВЕРЯЮЩЕГО для корректировки утверждённой субсидии — волна 3C
// (02.10.2026). Состояние одной открытой корректировки: детали/ops с сервера,
// решения проверяющего (принять/отклонить/исправить сумму), строки самого
// проверяющего («Снять с другой позиции»), пересчёт preview по ЭТИМ решениям
// (через provideRevisionReviewOverlay — useRevisionOverlay.ts, Правило №6:
// вторым способом считать «было/станет»/баланс не заводим), применение.
//
// Каскад «отклонил родителя → потомки тоже визуально отклонены» (требование
// владельца п.7): decide_and_apply сам помечает потомков auto_rejected, но
// ТОЛЬКО если им вообще не передано решение (см. docstring apply() ниже) —
// поэтому здесь дочерние строки отклонённого родителя (isBlocked) исключаются
// И из accepted_op_ids для /preview, И из decisions для /apply, а не
// отправляются как "accept" — иначе бэкенд ответит 422 на попытку принять
// дочернюю без принятого родителя (см. decide_and_apply, блок после разбора
// decisions).
import { computed, reactive, ref, watch, type Ref } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { provideRevisionReviewOverlay, type RevisionOverlayApi } from './useRevisionOverlay'
import type { RevisionOp, RevisionDetail } from './useSubsidyRevision'

// Поля, которые отдаёт GET /subsidy-revisions/{id} сверх базового RevisionOp
// (см. app/routers/subsidy_revisions.py::_op_dict) — тип черновика (волна 3B)
// их не перечислял, т.к. автору они не нужны.
export interface ReviewOp extends RevisionOp {
  depends_on_op_id: number | null
  applied_entity_id: number | null
  author_name: string | null
}

export interface ReviewDetail extends Omit<RevisionDetail, 'ops'> {
  ops: ReviewOp[]
  // Поля, которые GET /subsidy-revisions/{id} отдаёт сверх RevisionDetail
  // (useSubsidyRevision.ts описывал только то, что нужно автору).
  author_id: number | null
  author_name: string | null
  submitted_at: string | null
  closed_at: string | null
}

export interface RevisionTreeCategory {
  id: number
  name: string
  parent_id: number | null
  level: number
}

interface ExtraOpEntry {
  _key: string
  _label: string
  entity_type: 'feo_category' | 'feo_item'
  op_type: 'update'
  target_id: number
  after: Record<string, unknown>
  bundle_no: number | null
}

export interface ApplyOutcome {
  ok: boolean
  code?: string
  message?: string
  details?: any
}

export function useRevisionReview(revisionId: number) {
  const detail = ref<ReviewDetail | null>(null)
  const categories = ref<RevisionTreeCategory[]>([])
  const loadingDetail = ref(false)
  const loadingCategories = ref(false)
  const applying = ref(false)
  const error = ref<string | null>(null)

  // Решения проверяющего, пока не отправлены на /apply — живут только на
  // экране (checkbox «принять» по умолчанию включён для каждой pending-строки,
  // снятие галочки добавляет id сюда).
  const rejectedIds = reactive(new Set<number>())
  const comments = reactive<Record<number, string>>({})
  const overrides = reactive<Record<number, Record<string, unknown>>>({})
  const extraOps = reactive<ExtraOpEntry[]>([])

  const ops = computed<ReviewOp[]>(() => detail.value?.ops || [])
  const opsById = computed(() => new Map(ops.value.map((o) => [o.id, o])))
  const pendingOps = computed(() => ops.value.filter((o) => o.status === 'pending'))
  const decidedOps = computed(() => ops.value.filter((o) => o.status !== 'pending'))

  function isRejectedLocally(opId: number): boolean { return rejectedIds.has(opId) }

  // Отклонён ли кто-то из предков (create-категория/позиция, от которой
  // зависит эта строка) — либо решением проверяющего СЕЙЧАС, либо уже
  // закрытым решением прошлого прохода (rejected/auto_rejected).
  function isBlocked(op: ReviewOp): boolean {
    let cur: ReviewOp | undefined = op
    const seen = new Set<number>()
    while (cur?.depends_on_op_id != null && !seen.has(cur.depends_on_op_id)) {
      seen.add(cur.depends_on_op_id)
      const parent = opsById.value.get(cur.depends_on_op_id)
      if (!parent) return false
      if (parent.status === 'rejected' || parent.status === 'auto_rejected' || rejectedIds.has(parent.id)) return true
      cur = parent
    }
    return false
  }
  function blockingParentId(op: ReviewOp): number | null {
    let cur: ReviewOp | undefined = op
    const seen = new Set<number>()
    while (cur?.depends_on_op_id != null && !seen.has(cur.depends_on_op_id)) {
      seen.add(cur.depends_on_op_id)
      const parent = opsById.value.get(cur.depends_on_op_id)
      if (!parent) return null
      if (parent.status === 'rejected' || parent.status === 'auto_rejected' || rejectedIds.has(parent.id)) return parent.id
      cur = parent
    }
    return null
  }
  function isAccepted(op: ReviewOp): boolean { return !rejectedIds.has(op.id) && !isBlocked(op) }
  function toggleAccept(opId: number, accept: boolean): void {
    if (accept) rejectedIds.delete(opId)
    else rejectedIds.add(opId)
  }
  function setComment(opId: number, text: string): void { comments[opId] = text }
  function setOverride(opId: number, after: Record<string, unknown> | null): void {
    if (after && Object.keys(after).length) overrides[opId] = after
    else delete overrides[opId]
  }

  const acceptedOpIds = computed<number[]>(() =>
    pendingOps.value.filter((o) => isAccepted(o)).map((o) => o.id),
  )
  const reviewerOverridesBody = computed<Record<number, Record<string, unknown>>>(() => {
    const out: Record<number, Record<string, unknown>> = {}
    for (const op of pendingOps.value) {
      const ov = overrides[op.id]
      if (isAccepted(op) && ov) out[op.id] = ov
    }
    return out
  })
  const extraOpsBody = computed(() => extraOps.map(({ _key, _label, ...rest }) => rest))

  const revisionIdRef: Ref<number | null> = ref(revisionId)
  const overlay: RevisionOverlayApi = provideRevisionReviewOverlay(
    revisionIdRef,
    () => ({
      accepted_op_ids: acceptedOpIds.value,
      reviewer_overrides: reviewerOverridesBody.value,
      extra_ops: extraOpsBody.value,
    }),
    () => ops.value,
  )
  // Любое решение/правка суммы/строка проверяющего → пересчёт «станет»
  // (debounce 300мс внутри overlay.scheduleRefresh, см. useRevisionOverlay.ts).
  watch([acceptedOpIds, reviewerOverridesBody, extraOpsBody], () => overlay.scheduleRefresh(), { deep: true })

  async function loadDetail(): Promise<void> {
    loadingDetail.value = true
    try {
      detail.value = await apiFetch<ReviewDetail>(`/subsidy-revisions/${revisionId}`)
    } finally {
      loadingDetail.value = false
    }
  }
  async function loadCategories(): Promise<void> {
    if (!detail.value) return
    loadingCategories.value = true
    try {
      categories.value = await apiFetch<RevisionTreeCategory[]>(
        `/feo-categories/?subsidy_id=${detail.value.subsidy_id}`,
      )
    } finally {
      loadingCategories.value = false
    }
  }
  async function init(): Promise<void> {
    await loadDetail()
    await loadCategories()
    await overlay.refresh()
  }

  // Волна 3C-доп.: связь «узел дерева (категория/позиция) ↔ строка
  // корректировки» — ОДНО место поиска (Правило №6), используется и
  // RevisionTreeRow.vue (галочка/комментарий на строке дерева, клик →
  // прокрутка к строке связок), и RevisionReviewPanel.vue (клик по строке →
  // прокрутка к узлу дерева).
  function opForNode(kind: 'category' | 'item', id: number | string): ReviewOp | undefined {
    const entityType = kind === 'category' ? 'feo_category' : 'feo_item'
    const refMap = overlay.preview.value?.after?.ref_map || {}
    return ops.value.find((op) => {
      if (op.entity_type !== entityType) return false
      if (op.target_id != null) return String(op.target_id) === String(id)
      if (op.target_ref) return String(refMap[op.target_ref] ?? op.target_ref) === String(id)
      return false
    })
  }
  function nodeIdForOp(op: ReviewOp): number | string | null {
    if (op.target_id != null) return op.target_id
    if (op.target_ref) {
      const refMap = overlay.preview.value?.after?.ref_map || {}
      return refMap[op.target_ref] ?? op.target_ref
    }
    return null
  }

  const categoryById = computed(() => new Map(categories.value.map((c) => [c.id, c])))
  function categoryName(id: number | string | null | undefined): string {
    if (id == null) return '—'
    const found = categoryById.value.get(Number(id))
    if (found) return found.name
    // Ещё не существующая в живой БД категория (создаётся этой же
    // корректировкой) — имя берём из её собственной create-строки.
    const createOp = ops.value.find((o) => o.op_type === 'create' && o.entity_type === 'feo_category' && String(o.target_id) === String(id))
    return createOp?.after?.name || `Статья #${id}`
  }

  function addExtraOp(input: {
    kind: 'category' | 'item'
    targetId: number
    label: string
    currentAmount: number
    removeAmount: number
    bundleNo: number | null
  }): void {
    const field = input.kind === 'category' ? 'budget' : 'amount'
    extraOps.push({
      _key: `extra-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      _label: input.label,
      entity_type: input.kind === 'category' ? 'feo_category' : 'feo_item',
      op_type: 'update',
      target_id: input.targetId,
      after: { [field]: Math.max(0, input.currentAmount - input.removeAmount) },
      bundle_no: input.bundleNo,
    })
  }
  function removeExtraOp(key: string): void {
    const i = extraOps.findIndex((e) => e._key === key)
    if (i >= 0) extraOps.splice(i, 1)
  }

  function buildDecisions(): Record<number, { decision: 'accept' | 'reject'; comment?: string | null; reviewer_after?: Record<string, unknown> }> {
    const out: Record<number, { decision: 'accept' | 'reject'; comment?: string | null; reviewer_after?: Record<string, unknown> }> = {}
    for (const op of pendingOps.value) {
      if (isBlocked(op)) continue // каскад — решает бэкенд (_collect_dependents), см. докстринг файла
      if (rejectedIds.has(op.id)) {
        out[op.id] = { decision: 'reject', comment: comments[op.id] || null }
      } else {
        const entry: { decision: 'accept' | 'reject'; comment?: string | null; reviewer_after?: Record<string, unknown> } = { decision: 'accept' }
        if (comments[op.id]) entry.comment = comments[op.id]
        const ov = overrides[op.id]
        if (ov) entry.reviewer_after = ov
        out[op.id] = entry
      }
    }
    return out
  }

  async function apply(force = false): Promise<ApplyOutcome> {
    applying.value = true
    error.value = null
    try {
      const data = await apiFetch<any>(`/subsidy-revisions/${revisionId}/apply`, {
        method: 'POST',
        body: JSON.stringify({ decisions: buildDecisions(), extra_ops: extraOpsBody.value, force }),
        suppressErrorDialog: true,
      })
      extraOps.splice(0, extraOps.length)
      await loadDetail()
      await overlay.refresh()
      return { ok: true, details: data }
    } catch (e: any) {
      const code = e?.payload?.code || 'error'
      const message = describeApiError(e, { fallback: 'Не удалось применить решение по корректировке' })
      error.value = message
      return { ok: false, code, message, details: e?.payload?.details }
    } finally {
      applying.value = false
    }
  }

  async function rejectAll(comment: string): Promise<ApplyOutcome> {
    for (const op of pendingOps.value) {
      rejectedIds.add(op.id)
      if (comment) comments[op.id] = comment
    }
    return apply(false)
  }

  return {
    detail, categories, loadingDetail, loadingCategories, applying, error,
    ops, pendingOps, decidedOps, overlay,
    // comments/overrides — ОДИН источник (Правило №6): RevisionDiffTable.vue/
    // RevisionReviewPanel.vue читают и пишут ровно эти реактивные объекты
    // (через setComment/setOverride), второй копии в компонентах не заводим —
    // buildDecisions()/reviewerOverridesBody читают их же напрямую.
    comments, overrides,
    isRejectedLocally, isBlocked, blockingParentId, isAccepted, toggleAccept, setComment, setOverride,
    acceptedOpIds, extraOps, addExtraOp, removeExtraOp,
    init, loadDetail, loadCategories, categoryName, opForNode, nodeIdForOp,
    apply, rejectAll,
  }
}

export type RevisionReviewApi = ReturnType<typeof useRevisionReview>
