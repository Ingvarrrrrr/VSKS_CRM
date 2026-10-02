// Оверлей «было/станет» для дерева ФЭО под корректировкой — волна 3B. Один
// разбор ответа /subsidy-revisions/{id}/preview (Правило №6: если бэкенд
// отдаст форму чуть иначе — править ТОЛЬКО здесь, FeoTreeRow.vue/
// RevisionTotalsHeader.vue читают уже нормализованные методы, не сырой JSON).
//
// provide/inject: SubsidiesView.vue зовёт provideRevisionOverlay(...) один раз
// (ctx строится там же, что и остальной SubsidyDetailContext), FeoTreeTable.vue/
// FeoTreeRow.vue читают useRevisionOverlay() — то же разделение, что и
// useSubsidyDetailCtx(), но отдельным инжектом, чтобы не раздувать уже
// полновесный SubsidyDetailContext новым обязательным полем (эти два файла и
// так в списке «править вставками»).
import { inject, provide, ref, watch, type InjectionKey, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { RevisionOp } from './useSubsidyRevision'

export interface RevisionPreviewBag {
  nodes: Record<string, Record<string, any>>
  items: Record<string, Record<string, any>>
  totals: Record<string, number>
  // Только у "after" (см. subsidy_revision_preview.py::preview) — ref:id для
  // ещё не сохранённых create-строк ("c3"/"i3" → реальный id в этом прогоне).
  ref_map?: Record<string, number>
}

export interface RevisionBundle {
  // Волна 3D: ЦЕЛОЕ число («Связка 1»), не строка — см. докстринг
  // RevisionOp.bundle_no в useSubsidyRevision.ts.
  bundle_no: number
  added: number
  removed: number
  balance: number
  // Волна 3C: бэкенд (subsidy_revision_floor.py::compute_balance) отдаёт
  // shortfall НА КАЖДУЮ связку, не только в сумме — отсутствовало в типе,
  // вставленном волной 3B (там shortfall ещё не читали). Правка ТОЛЬКО здесь
  // (Правило №6) — RevisionBundleDialog.vue/RevisionDraftBar.vue читают
  // bundles тем же полем, просто не используют shortfall.
  shortfall: number
}

export interface RevisionBalance {
  free_before: number
  free_after: number
  shortfall: number
  can_apply: boolean
}

export interface RevisionPreview {
  before: RevisionPreviewBag
  after: RevisionPreviewBag
  changed: { categories: Array<number | string>; items: Array<number | string> }
  ancestors: number[]
  bundles: RevisionBundle[]
  // Волна 3C: верхнеуровневый `balance` отсутствовал в типе волны 3B (сама
  // она его не читала) — POST /preview реально его отдаёт (см.
  // subsidy_revision_preview.py::preview, ключ "balance" без "bundles"
  // внутри). Экран проверяющего завязан на free_before/free_after/can_apply.
  balance: RevisionBalance
  problems: Array<{ op_id: number | string; code: string; message: string }>
  can_apply: boolean
  elapsed_ms: number
}

export interface RevisionOverlayApi {
  active: Ref<boolean>
  loading: Ref<boolean>
  preview: Ref<RevisionPreview | null>
  refresh: () => Promise<void>
  scheduleRefresh: () => void
  beforeFieldFor: (kind: 'category' | 'item', id: number | string, field: string) => number | null
  afterFieldFor: (kind: 'category' | 'item', id: number | string, field: string) => number | null
  isChangedRow: (kind: 'category' | 'item', id: number | string) => boolean
  isAncestorCategory: (categoryId: number) => boolean
  isNewRow: (kind: 'category' | 'item', id: number | string) => boolean
  isDeletedRow: (kind: 'category' | 'item', id: number | string) => boolean
  deleteReason: (kind: 'category' | 'item', id: number | string) => string | null
}

const REVISION_OVERLAY_KEY: InjectionKey<RevisionOverlayApi> = Symbol('revisionOverlay')

/** Общая часть RevisionOverlayApi, не завязанная на ТО, как именно обновляется
 * preview (черновик автора дёргает /preview без тела, экран проверяющего —
 * с accepted_op_ids/reviewer_overrides/extra_ops, см.
 * provideRevisionReviewOverlay ниже) — вынесено, чтобы не писать одни и те же
 * beforeFieldFor/isChangedRow/isNewRow и т.п. дважды (Правило №6). */
function buildOverlayCore(preview: Ref<RevisionPreview | null>, getOps: () => RevisionOp[]) {
  function bagKey(kind: 'category' | 'item') { return kind === 'category' ? 'nodes' : 'items' }

  function nodeAfter(kind: 'category' | 'item', id: number | string) {
    return preview.value?.after?.[bagKey(kind)]?.[String(id)] ?? null
  }
  function nodeBefore(kind: 'category' | 'item', id: number | string) {
    return preview.value?.before?.[bagKey(kind)]?.[String(id)] ?? null
  }
  function beforeFieldFor(kind: 'category' | 'item', id: number | string, field: string): number | null {
    const n = nodeBefore(kind, id)
    return n && n[field] != null ? Number(n[field]) : null
  }
  function afterFieldFor(kind: 'category' | 'item', id: number | string, field: string): number | null {
    const n = nodeAfter(kind, id)
    return n && n[field] != null ? Number(n[field]) : null
  }
  function isChangedRow(kind: 'category' | 'item', id: number | string): boolean {
    const list = kind === 'category' ? preview.value?.changed?.categories : preview.value?.changed?.items
    return !!list?.some((x) => String(x) === String(id))
  }
  function isAncestorCategory(categoryId: number): boolean {
    return !!preview.value?.ancestors?.includes(categoryId)
  }
  // Новая строка — её id это ТОЛЬКО fake-ref ("c3"/"i3"), числовых id из БД у
  // неё ещё нет; либо явный флаг операции create на этом ref.
  function isNewRow(kind: 'category' | 'item', id: number | string): boolean {
    if (typeof id === 'string' && /^[a-z]/i.test(id)) return true
    const entityType = kind === 'category' ? 'feo_category' : 'feo_item'
    return getOps().some((op) => op.op_type === 'create' && op.entity_type === entityType && op.target_ref === String(id))
  }
  function matchingDeleteOp(kind: 'category' | 'item', id: number | string): RevisionOp | undefined {
    const entityType = kind === 'category' ? 'feo_category' : 'feo_item'
    return getOps().find((op) => op.op_type === 'delete' && op.entity_type === entityType
      && (String(op.target_id) === String(id) || op.target_ref === String(id)))
  }
  function isDeletedRow(kind: 'category' | 'item', id: number | string): boolean {
    return !!matchingDeleteOp(kind, id)
  }
  function deleteReason(kind: 'category' | 'item', id: number | string): string | null {
    return matchingDeleteOp(kind, id)?.review_comment ?? null
  }

  return { beforeFieldFor, afterFieldFor, isChangedRow, isAncestorCategory, isNewRow, isDeletedRow, deleteReason }
}

/** getDraftId — колбэк (не просто число): draftId может появиться позже
 * (первая правка создаёт черновик лениво), overlay должен подхватить его
 * рефреш, не пересоздаваясь. getOps — текущий список операций черновика
 * (useSubsidyRevision().state.detail?.ops ?? []) — используется для
 * isNewRow/isDeletedRow/deleteReason без повторного похода на preview. */
export function provideRevisionOverlay(getDraftId: () => number | null, getOps: () => RevisionOp[], opsVersion?: Ref<number>): RevisionOverlayApi {
  const active = ref(false)
  const loading = ref(false)
  const preview = ref<RevisionPreview | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let reqSeq = 0

  async function refresh(): Promise<void> {
    const draftId = getDraftId()
    if (!draftId) { active.value = false; preview.value = null; return }
    const seq = ++reqSeq
    loading.value = true
    try {
      const res = await apiFetch<RevisionPreview>(`/subsidy-revisions/${draftId}/preview`, {
        method: 'POST', body: JSON.stringify({}),
      })
      if (seq !== reqSeq) return // устаревший ответ — пришла более новая правка
      preview.value = res
      active.value = true
    } catch {
      // Отказ предпросмотра не должен ронять экран дерева — остаёмся на
      // прошлом preview (пользователь увидит спиннер пропавшим, но «станет»
      // не обнулится).
    } finally {
      if (seq === reqSeq) loading.value = false
    }
  }

  function scheduleRefresh(): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(refresh, 300)
  }

  const api: RevisionOverlayApi = {
    active, loading, preview, refresh, scheduleRefresh,
    ...buildOverlayCore(preview, getOps),
  }
  // Любая правка через feoWriteAdapter.ts бьёт opsVersion (useSubsidyRevision.ts)
  // — подписываемся здесь, а не в каждом месте записи (useFeoTreeDnd.ts/
  // useFeoLevel5.ts и т.п. не обязаны знать про overlay вообще).
  if (opsVersion) watch(opsVersion, () => scheduleRefresh())
  provide(REVISION_OVERLAY_KEY, api)
  return api
}

export interface RevisionReviewPreviewBody {
  accepted_op_ids?: number[]
  reviewer_overrides?: Record<number, Record<string, unknown>>
  extra_ops?: Array<Record<string, unknown>>
}

/**
 * Волна 3C — тот же RevisionOverlayApi (тот же REVISION_OVERLAY_KEY, те же
 * RevisionCellBadge.vue/RevisionTotalsHeader.vue умеют его читать без
 * изменений), но refresh() сам решает ЧТО слать в тело /preview — экран
 * проверяющего пересчитывает «станет» только по строкам, которые сейчас
 * отмечены «принять» (+ ещё не сохранённые extra_ops проверяющего), см.
 * useRevisionReview.ts::scheduleRefresh. provideRevisionOverlay() (автор)
 * использует отдельный путь (тело всегда {}) — здесь НЕ переиспользован,
 * потому что тело запроса там принципиально другое, но вся остальная логика
 * (beforeFieldFor/isChangedRow/...) — buildOverlayCore, один источник
 * (Правило №6).
 */
export function provideRevisionReviewOverlay(
  revisionId: Ref<number | null>,
  getBody: () => RevisionReviewPreviewBody,
  getOps: () => RevisionOp[],
): RevisionOverlayApi {
  const active = ref(false)
  const loading = ref(false)
  const preview = ref<RevisionPreview | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let reqSeq = 0
  // Приёмка 02.10, п.5: пересчёт у проверяющего уходил на ~2.5с на каждое
  // решение — ВСЯ эта работа перечитывала "before" заново, хотя оно не
  // меняется, пока открыт этот экран (живые данные правит только apply()).
  // После первого успешного ответа просим бэкенд больше его не пересчитывать
  // (include_before:false) и держим прежний preview.before локально.
  let gotBefore = false

  async function refresh(): Promise<void> {
    const id = revisionId.value
    if (!id) { active.value = false; preview.value = null; return }
    const seq = ++reqSeq
    loading.value = true
    try {
      const res = await apiFetch<RevisionPreview>(`/subsidy-revisions/${id}/preview`, {
        method: 'POST', body: JSON.stringify({ ...getBody(), include_before: !gotBefore }),
      })
      if (seq !== reqSeq) return
      preview.value = gotBefore ? { ...res, before: preview.value?.before ?? res.before } : res
      gotBefore = true
      active.value = true
    } catch {
      // Как и у автора — не роняем экран, остаёмся на прошлом preview.
    } finally {
      if (seq === reqSeq) loading.value = false
    }
  }
  function scheduleRefresh(): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(refresh, 300)
  }
  // Сменилась сама корректировка (навигация между карточками проверки) —
  // "before" снова нужен с нуля, иначе переиспользуем before предыдущей.
  watch(revisionId, () => { gotBefore = false })

  const api: RevisionOverlayApi = {
    active, loading, preview, refresh, scheduleRefresh,
    ...buildOverlayCore(preview, getOps),
  }
  provide(REVISION_OVERLAY_KEY, api)
  return api
}

export function useRevisionOverlay(): RevisionOverlayApi | null {
  return inject(REVISION_OVERLAY_KEY, null)
}
