// Единственная точка записи дерева ФЭО/субсидии (Правило №6) — волна 3B,
// «Корректировка утверждённой субсидии через проверку». Все места, что раньше
// слали apiFetch(PUT/POST/DELETE ...) прямо из useFeoTreeDnd.ts/useFeoLevel5.ts/
// useFeoPlannedItemEditDialog.ts/useFeoPlannedItemAddDialog.ts/SubsidyEditDialog.vue,
// теперь решают через getAdapterMode(subsidyId):
//  - 'direct'    — поведение НЕ меняется: вызывающий сам шлёт свой обычный
//                  apiFetch (передаётся сюда как колбэк `direct`), адаптер
//                  только оборачивает его в единый {ok,...}-результат;
//  - 'revision'  — вместо прямого запроса в БД летит POST .../ops (создав
//                  черновик корректировки при самой первой правке) — ТОЛЬКО
//                  изменённые поля (fields/payload, не полный снимок узла);
//                  живое дерево НЕ трогаем, «станет» считает useRevisionOverlay.ts
//                  через /preview;
//  - 'forbidden' — ничего не шлём, понятная причина для UI.
//
// Создание/перенос/удаление категории или позиции через корректировку даёт
// только что созданной сущности строковый target_ref («c3»/«i3») вместо
// числового id — его нужно использовать в ПОСЛЕДУЮЩИХ правках той же строки
// (adapter сам запоминает маппинг через registerFakeRef/resolveTarget).
import { getRevisionMode, postRevisionOp, type AdapterOpInput } from './useSubsidyRevision'
// postRevisionOp теперь отдаёт RevisionOpAck (волна 3D) — см. докстринг там же,
// здесь из него читаем только target_ref, тип не импортируем отдельно.

// Реэкспорт НЕ создаёт локальное имя в этом модуле (`export { x as y }` не то
// же самое, что `const y = x`) — используем прямой alias для вызовов ниже.
export const getAdapterMode = getRevisionMode

export type AdapterResult<T> = { ok: true; mode: 'direct' | 'revision'; item?: T; targetRef?: string } | { ok: false; error: string }

// ── fake-id ↔ target_ref для сущностей, созданных ВНУТРИ текущей корректировки
// (ещё не существующих в живой таблице) — module-level, переживает смену
// компонента (создали категорию, диалог закрылся, но дальше с ней работают
// из дерева). Сбрасывается только перезагрузкой страницы — приемлемо: fake-id
// уникален в рамках одной открытой корректировки.
let fakeIdCounter = -1
const fakeIdToRef = new Map<number, string>()

export function nextFakeId(ref: string): number {
  const id = fakeIdCounter--
  fakeIdToRef.set(id, ref)
  return id
}

export function getFakeIdForRef(ref: string): number | undefined {
  for (const [id, r] of fakeIdToRef) if (r === ref) return id
  return undefined
}

function resolveTarget(id: number): { targetId?: number; targetRef?: string } {
  const ref = fakeIdToRef.get(id)
  return ref ? { targetRef: ref } : { targetId: id }
}

function describeError(e: any, fallback: string): string {
  return e?.payload?.message || e?.detail || e?.message || fallback
}

async function runDirect<T>(direct: () => Promise<T>): Promise<AdapterResult<T>> {
  try {
    const item = await direct()
    return { ok: true, mode: 'direct', item }
  } catch (e: any) {
    return { ok: false, error: describeError(e, 'Ошибка сохранения') }
  }
}

async function runOp(subsidyId: number, input: AdapterOpInput): Promise<AdapterResult<never>> {
  try {
    const op = await postRevisionOp(subsidyId, input)
    return { ok: true, mode: 'revision', targetRef: op.target_ref || undefined }
  } catch (e: any) {
    return { ok: false, error: describeError(e, 'Не удалось сохранить правку в корректировку') }
  }
}

interface DispatchArgs<T> {
  subsidyId: number | null | undefined
  entityType: AdapterOpInput['entityType']
  opType: AdapterOpInput['opType']
  targetId?: number
  parentId?: number | null
  after?: Record<string, unknown>
  bundleNo?: number
  direct: () => Promise<T>
}

/** Общий диспетчер — используется специализированными хелперами ниже. Прямой
 * режим (и когда subsidyId неизвестен/контекст ещё не загружен) идентичен
 * поведению ДО волны 3B — просто зовёт `direct()`. */
export async function dispatchFeoWrite<T>(args: DispatchArgs<T>): Promise<AdapterResult<T>> {
  const mode = getAdapterMode(args.subsidyId)
  if (mode === 'forbidden') {
    return { ok: false, error: 'Нет права корректировать субсидию' }
  }
  if (mode !== 'revision') {
    return runDirect(args.direct)
  }
  const subsidyId = args.subsidyId as number
  const target = args.targetId != null ? resolveTarget(args.targetId) : {}
  const parentRef = args.parentId != null ? (fakeIdToRef.get(args.parentId) ?? undefined) : undefined
  const res = await runOp(subsidyId, {
    entityType: args.entityType,
    opType: args.opType,
    targetId: target.targetId,
    targetRef: target.targetRef,
    parentRef: args.parentId != null && !parentRef ? undefined : parentRef,
    after: args.after,
    bundleNo: args.bundleNo,
  })
  if (!res.ok) return res
  if (args.opType === 'create' && res.targetRef) {
    // Присвоим созданной сущности fake-id, чтобы дальнейшие правки (ещё в этой
    // же сессии, до перезагрузки дерева) могли адресоваться по нему.
    nextFakeId(res.targetRef)
  }
  return res as AdapterResult<T>
}

// ── Специализированные хелперы — тонкие обёртки над dispatchFeoWrite с
// именами, соответствующими вызывающим местам (useFeoTreeDnd.ts/useFeoLevel5.ts) ──

export function updateFeoCategory<T>(subsidyId: number | null | undefined, nodeId: number, fields: Record<string, unknown>, direct: () => Promise<T>) {
  return dispatchFeoWrite({
    subsidyId, entityType: 'feo_category', opType: 'update', targetId: nodeId,
    after: fields, direct,
  })
}

export function createFeoCategory<T>(subsidyId: number | null | undefined, parentId: number | null, payload: Record<string, unknown>, direct: () => Promise<T>) {
  return dispatchFeoWrite({
    subsidyId, entityType: 'feo_category', opType: 'create', parentId: parentId ?? undefined,
    after: payload, direct,
  })
}

export function deleteFeoCategory(subsidyId: number | null | undefined, nodeId: number, direct: () => Promise<void>) {
  return dispatchFeoWrite({ subsidyId, entityType: 'feo_category', opType: 'delete', targetId: nodeId, direct })
}

export function moveFeoCategory<T>(subsidyId: number | null | undefined, nodeId: number, parentId: number | null, direct: () => Promise<T>) {
  return dispatchFeoWrite({
    subsidyId, entityType: 'feo_category', opType: 'move', targetId: nodeId, parentId: parentId ?? undefined,
    after: { parent_id: parentId }, direct,
  })
}

export function updateFeoItem<T>(subsidyId: number | null | undefined, itemId: number, fields: Record<string, unknown>, direct: () => Promise<T>) {
  return dispatchFeoWrite({
    subsidyId, entityType: 'feo_item', opType: 'update', targetId: itemId,
    after: fields, direct,
  })
}

export function createFeoItem<T>(subsidyId: number | null | undefined, parentCategoryId: number | null, payload: Record<string, unknown>, direct: () => Promise<T>) {
  return dispatchFeoWrite({
    subsidyId, entityType: 'feo_item', opType: 'create', parentId: parentCategoryId ?? undefined,
    after: payload, direct,
  })
}

export function deleteFeoItem(subsidyId: number | null | undefined, itemId: number, direct: () => Promise<void>) {
  return dispatchFeoWrite({ subsidyId, entityType: 'feo_item', opType: 'delete', targetId: itemId, direct })
}

export function updateSubsidyFields<T>(subsidyId: number | null | undefined, fields: Record<string, unknown>, direct: () => Promise<T>) {
  return dispatchFeoWrite({
    subsidyId, entityType: 'subsidy', opType: 'update', targetId: subsidyId ?? undefined,
    after: fields, direct,
  })
}

/** В revision-режиме локальное дерево НЕ мутируем живыми значениями (владелец:
 * «было» остаётся живым деревом, «станет» — из /preview) — вызывающие места
 * должны пропускать свой обычный `cat.field = val` блок, когда это true. */
export function isRevisionMode(subsidyId: number | null | undefined): boolean {
  return getAdapterMode(subsidyId) === 'revision'
}

export function isForbiddenMode(subsidyId: number | null | undefined): boolean {
  return getAdapterMode(subsidyId) === 'forbidden'
}
