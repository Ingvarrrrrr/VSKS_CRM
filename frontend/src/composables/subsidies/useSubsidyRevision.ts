// Корректировка утверждённой субсидии через проверку — волна 3B (исполнитель,
// 2026-10-02). Состояние по /subsidy-revisions/* (контекст/черновик/операции),
// общее для feoWriteAdapter.ts (решает direct/revision по этому же состоянию)
// и RevisionDraftBar.vue/useRevisionOverlay.ts (показывают его). Module-level
// Map по subsidy_id (не makeCtxSingleton — несколько субсидий могут быть
// просмотрены за сессию, хотя активна всегда одна), тот же приём, что и
// feoPlanChangeBus.ts/useFeoUndoStack.ts — единственный источник этого
// состояния (Правило №6), второй копии в компонентах не заводим.
import { reactive } from 'vue'
import { apiFetch } from '@/api'

export type RevisionMode = 'direct' | 'revision' | 'forbidden'

export interface RevisionDraftSummary {
  id: number
  number: number
  status: string
  ops_count: number
}

export interface RevisionPendingSummary {
  id: number
  number: number
  author_name: string
  submitted_at: string
  ops_count: number
}

export interface RevisionContext {
  mode: RevisionMode
  can_approve: boolean
  draft: RevisionDraftSummary | null
  pending_review: RevisionPendingSummary[]
}

export interface RevisionOp {
  id: number
  seq: number
  op_type: 'create' | 'update' | 'delete' | 'move'
  entity_type: 'subsidy' | 'feo_category' | 'feo_item'
  target_id: number | null
  target_ref: string | null
  parent_ref: string | null
  field_group: string | null
  path: string | null
  before: any
  after: any
  reviewer_after: any
  status: string
  // Волна 3D (приёмка 02.10): bundle_no — ЦЕЛОЕ число («Связка 1»), не строка —
  // бэкенд назначает его через POST /subsidy-revisions/{id}/bundles.
  bundle_no: number | null
  added_by_reviewer: boolean
  review_comment: string | null
}

export interface RevisionDetail {
  id: number
  number: number
  status: string
  subsidy_id: number
  author_comment: string | null
  reviewer_comment: string | null
  ops: RevisionOp[]
}

export interface AdapterOpInput {
  entityType: 'subsidy' | 'feo_category' | 'feo_item'
  opType: 'create' | 'update' | 'delete' | 'move'
  targetId?: number
  targetRef?: string
  parentRef?: string
  after?: Record<string, unknown>
  bundleNo?: number
}

/** Ответ POST .../ops — минимальный «ack» на созданную/изменённую строку (не
 * полный RevisionOp: GET .../{id} следом отдаёт настоящий детальный список,
 * см. loadDetailInto). Волна 3D (бэкенд-исполнитель, подтверждено 02.10):
 * без обязательного field_group одна правка может лечь в НЕСКОЛЬКО групп
 * полей — тогда бэкенд отвечает {id, target_ref, status, ops:[{id,
 * target_ref, status, field_group}, ...]} (верхний уровень — первая группа,
 * `ops` — полный список всех созданных строк); одна группа — просто {id,
 * target_ref, status} без `ops`. normalizeOpsAck — ЕДИНСТВЕННОЕ место разбора
 * этой вилки (Правило №6): при наличии `ops` берём его целиком (там уже есть
 * и первая группа), иначе — сам верхний объект.
 *
 * sync_product_kind/product_id/allow_duplicate_name (служебные флаги запроса
 * позиции, не поля сущности) бэкенд теперь отбрасывает сам — фронт их всё
 * равно не шлёт в revisionFields (см. useFeoPlannedItemEditDialog.ts/
 * useFeoLevel5ItemType.ts), чтобы diff строки корректировки оставался чистым
 * (не «Sync product kind: да» в списке изменений). Любое ДРУГОЕ неизвестное
 * поле бэкенд отклоняет 422 {code:'unknown_field'} — до ops уходят только
 * реальные поля FeoPlannedItemCreate/FeoCategory/Subsidy-схем. */
export interface RevisionOpAck {
  id: number | null
  target_ref?: string | null
  status?: string
  field_group?: string | null
  message?: string
}

function normalizeOpsAck(raw: any): RevisionOpAck[] {
  if (raw && Array.isArray(raw.ops)) return raw.ops
  if (Array.isArray(raw)) return raw // защитный случай — бэкенд пока не подтверждал голый массив, но парсим на всякий
  return raw ? [raw] : []
}

interface SubsidyRevisionState {
  subsidyId: number
  context: RevisionContext | null
  detail: RevisionDetail | null
  loadingContext: boolean
  loadingDetail: boolean
  error: string | null
  // Счётчик версий ops — useRevisionOverlay.ts следит за ним и пере-дёргивает
  // /preview (debounce), не завязываясь на то, ЧТО именно изменилось.
  opsVersion: number
}

const states = reactive(new Map<number, SubsidyRevisionState>())

function ensureState(subsidyId: number): SubsidyRevisionState {
  let st = states.get(subsidyId)
  if (!st) {
    st = reactive({
      subsidyId, context: null, detail: null,
      loadingContext: false, loadingDetail: false, error: null, opsVersion: 0,
    }) as SubsidyRevisionState
    states.set(subsidyId, st)
  }
  return st
}

/** Для feoWriteAdapter.ts — синхронное чтение текущего режима без реактивной подписки. */
export function getRevisionState(subsidyId: number): SubsidyRevisionState | null {
  return states.get(subsidyId) || null
}

export function getRevisionMode(subsidyId: number | null | undefined): RevisionMode {
  if (!subsidyId) return 'direct'
  const st = states.get(subsidyId)
  // Контекст ещё не загружен (экран только открылся, фича выключена, или этот
  // subsidyId вообще не инициализировал useSubsidyRevision) — ведём себя как
  // раньше, направление определяет только явный ответ /context.
  if (!st || !st.context) return 'direct'
  return st.context.mode
}

async function loadDetailInto(st: SubsidyRevisionState): Promise<void> {
  const draftId = st.context?.draft?.id
  if (!draftId) { st.detail = null; return }
  st.loadingDetail = true
  try {
    st.detail = await apiFetch<RevisionDetail>(`/subsidy-revisions/${draftId}`)
  } finally {
    st.loadingDetail = false
  }
}

/** Создаёт черновик при первой правке (ленивая инициализация) — используется
 * и composable'ом useSubsidyRevision ниже, и feoWriteAdapter.ts напрямую (ему
 * не нужен полный реактивный API, только id черновика). */
export async function ensureDraftForSubsidy(subsidyId: number): Promise<number> {
  const st = ensureState(subsidyId)
  if (st.context?.draft?.id) return st.context.draft.id
  const draft = await apiFetch<{ id: number; number: number; status: string; ops_count?: number }>(
    '/subsidy-revisions/draft',
    { method: 'POST', body: JSON.stringify({ subsidy_id: subsidyId }) },
  )
  if (!st.context) st.context = { mode: 'revision', can_approve: false, draft: null, pending_review: [] }
  st.context.draft = { id: draft.id, number: draft.number, status: draft.status || 'draft', ops_count: draft.ops_count ?? 0 }
  await loadDetailInto(st)
  return draft.id
}

/** Единственная точка POST .../ops (Правило №6) — feoWriteAdapter.ts и
 * useSubsidyRevision().addOp зовут РОВНО эту функцию. */
export async function postRevisionOp(subsidyId: number, input: AdapterOpInput): Promise<RevisionOpAck> {
  const draftId = await ensureDraftForSubsidy(subsidyId)
  const st = ensureState(subsidyId)
  // field_group НЕ отправляем (волна 3D) — бэкенд сам раскладывает поля по
  // группам, не завязываясь на то, что фронт угадал их join через запятую.
  const raw = await apiFetch<any>(`/subsidy-revisions/${draftId}/ops`, {
    method: 'POST',
    body: JSON.stringify({
      entity_type: input.entityType,
      op_type: input.opType,
      target_id: input.targetId ?? null,
      target_ref: input.targetRef ?? null,
      parent_ref: input.parentRef ?? null,
      after: input.after ?? {},
      bundle_no: input.bundleNo ?? null,
    }),
  })
  const acks = normalizeOpsAck(raw)
  st.opsVersion += 1
  await loadDetailInto(st)
  // «Первичная» строка — та, у которой есть target_ref (создание сущности,
  // нужен feoWriteAdapter.ts::nextFakeId); иначе первая из ответа.
  return acks.find((a) => a?.target_ref) || acks[0] || { id: null }
}

/** Связка «откуда деньги» — волна 3D. Один HTTP-вызов (Правило №6), используется
 * и useSubsidyRevision().createBundle (автор создаёт связку через
 * RevisionBundleDialog.vue/RevisionDraftBar.vue), и useRevisionReview.ts
 * (проверяющий — «Снять с другой позиции» идёт через extra_ops/apply, но та же
 * форма ответа {bundle_no}, если когда-нибудь понадобится явный вызов отсюда). */
export async function postRevisionBundle(revisionId: number, opIds: number[], freeMoney: boolean): Promise<{ bundle_no: number }> {
  return apiFetch<{ bundle_no: number }>(`/subsidy-revisions/${revisionId}/bundles`, {
    method: 'POST',
    body: JSON.stringify({ op_ids: opIds, free_money: freeMoney }),
  })
}

export function useSubsidyRevision(subsidyId: number) {
  const st = ensureState(subsidyId)

  async function loadContext(): Promise<void> {
    st.loadingContext = true
    st.error = null
    try {
      st.context = await apiFetch<RevisionContext>(`/subsidy-revisions/context?subsidy_id=${subsidyId}`)
      if (st.context.draft?.id) await loadDetailInto(st)
      else st.detail = null
    } catch (e: any) {
      // Эндпоинт пока не развёрнут бэкендом / фича выключена — тихо считаем
      // режим «прямой правки» (поведение как раньше), не блокируем экран.
      st.context = { mode: 'direct', can_approve: false, draft: null, pending_review: [] }
      st.error = e?.payload?.message || e?.detail || e?.message || null
    } finally {
      st.loadingContext = false
    }
  }

  async function createDraft(): Promise<void> {
    await ensureDraftForSubsidy(subsidyId)
  }

  async function addOp(input: AdapterOpInput): Promise<RevisionOpAck> {
    return postRevisionOp(subsidyId, input)
  }

  async function removeOp(opId: number): Promise<void> {
    const draftId = st.context?.draft?.id
    if (!draftId) return
    await apiFetch(`/subsidy-revisions/${draftId}/ops/${opId}`, { method: 'DELETE' })
    st.opsVersion += 1
    await loadDetailInto(st)
  }

  /** Присоединить строку к уже существующей связке (или отвязать, bundleNo=null)
   * — PATCH меняет только эту строку. Создание НОВОЙ связки — createBundle ниже
   * (другой эндпоинт, другая семантика: назначает bundle_no сразу нескольким
   * строкам). */
  async function setBundle(opId: number, bundleNo: number | null): Promise<void> {
    const draftId = st.context?.draft?.id
    if (!draftId) return
    await apiFetch(`/subsidy-revisions/${draftId}/ops/${opId}`, {
      method: 'PATCH', body: JSON.stringify({ bundle_no: bundleNo }),
    })
    st.opsVersion += 1
    await loadDetailInto(st)
  }

  /** Новая связка «откуда деньги» — волна 3D, требование владельца п.4
   * (RevisionBundleDialog.vue). opIds — строки, которые войдут в связку
   * (строка-увеличение + опционально строки-снятия); freeMoney=true — связка
   * без строк-источников, баланс сверяется со свободными деньгами субсидии. */
  async function createBundle(opIds: number[], freeMoney: boolean): Promise<number | null> {
    const draftId = st.context?.draft?.id
    if (!draftId) return null
    const res = await postRevisionBundle(draftId, opIds, freeMoney)
    st.opsVersion += 1
    await loadDetailInto(st)
    return res.bundle_no
  }

  async function submit(comment?: string): Promise<{ ok: true } | { ok: false; error: string; problems?: Array<{ op_id: number | string; code: string; message: string }> }> {
    const draftId = st.context?.draft?.id
    if (!draftId) return { ok: false, error: 'Нет корректировки для отправки' }
    try {
      await apiFetch(`/subsidy-revisions/${draftId}/submit`, { method: 'POST', body: JSON.stringify({ comment: comment ?? null }), suppressErrorDialog: true })
      await loadContext()
      return { ok: true }
    } catch (e: any) {
      // Волна 3D (приёмка п.6): бэкенд на 422 отвечает {code:'revision_problems',
      // problems:[{op_id, code, message}]} — err.payload.details несёт этот
      // объект целиком (см. api.ts::apiFetch, structuredDetail), RevisionDraftBar.vue
      // показывает problems у строк со стрелкой, не generic текстом.
      const details = e?.payload?.details
      const problems = details && details.code === 'revision_problems' ? details.problems : undefined
      return {
        ok: false,
        error: e?.payload?.message || e?.detail || e?.message || 'Не удалось отправить на проверку',
        problems,
      }
    }
  }

  async function withdraw(): Promise<{ ok: true } | { ok: false; error: string }> {
    const draftId = st.context?.draft?.id
    if (!draftId) return { ok: false, error: 'Нет корректировки для отзыва' }
    try {
      await apiFetch(`/subsidy-revisions/${draftId}/withdraw`, { method: 'POST' })
      await loadContext()
      return { ok: true }
    } catch (e: any) {
      return { ok: false, error: e?.payload?.message || e?.detail || e?.message || 'Не удалось отозвать с проверки' }
    }
  }

  return { state: st, loadContext, createDraft, addOp, removeOp, setBundle, createBundle, submit, withdraw }
}

export type SubsidyRevisionApi = ReturnType<typeof useSubsidyRevision>
