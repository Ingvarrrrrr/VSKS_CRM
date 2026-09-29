// useApproverCascade.ts — ОДИН источник истины для двух РАЗНЫХ действий с
// согласующими (ПРАВИЛО №6: раньше обвязка над ними была продублирована в
// useWishApprovers.ts (обычная заявка) и useAdvanceReimbursement.ts (заявка-
// компаньон авансового отчёта) — теперь оба зовут отсюда):
//   1) callApproverCascade — POST /wishes/{id}/approvers/cascade, строит
//      ВОСХОДЯЩУЮ цепочку начальников. Вызывается ТОЛЬКО кнопкой «Построить
//      цепочку» — по явному желанию пользователя, см. runCascade в обоих
//      композаблах.
//   2) ensureApproversBeforeSubmit — на «Отправить на согласование»: если
//      согласующих ещё нет, а поле «Верхний согласующий» заполнено, добавляет
//      ЭТОГО ОДНОГО человека единственным согласующим (тот же POST
//      /wishes/{id}/approvers, что и кнопка «Добавить согласующего»). Цепочку
//      САМА НЕ строит.
//
// Владелец (прод, заявка №85, 2026-09-29, первая правка): «автоматическое
// сохранение почему не происходит?» — но следующая правка коммита 534676a0
// (в тот же день) заставила ensureApproversBeforeSubmit звать cascade, и
// владелец это ОТМЕНИЛ: «Цепочка строится только по желанию — кнопкой
// «Построить цепочку». Если выбран один согласующий — он и остаётся
// единственным. Выбран Цыганов — всё, больше никого не надо». Отправка добавляет
// ровно выбранного человека, восходящую цепочку он получает только явным
// нажатием «Построить цепочку».
export interface CascadeApprover {
  id: number
  wish_id: number
  user_id: number | null
  order_num: number
  role_name: string | null
  full_name: string | null
  is_auto: boolean
  status: string
  comment: string | null
  decided_at: string | null
  decided_by_user_id: number | null
  decided_by_name?: string | null
  is_on_behalf?: boolean
}

export interface CascadeResult<A extends CascadeApprover = CascadeApprover> {
  approval_mode: string
  approvers: A[]
  warning?: string | null
}

export async function callApproverCascade<A extends CascadeApprover = CascadeApprover>(
  apiFetch: typeof import('@/api').apiFetch,
  wishId: number,
  topUserId: number,
  mode: 'sequential' | 'parallel',
): Promise<CascadeResult<A>> {
  return apiFetch<CascadeResult<A>>(
    `/wishes/${wishId}/approvers/cascade`,
    { method: 'POST', body: JSON.stringify({ top_user_id: topUserId, mode }) },
  )
}

// Перестановка согласующих местами (стрелки вверх/вниз) — владелец: «Согласующих
// можно менять местами только при последовательном согласовании» (parallel — все
// решают одновременно, порядок не имеет смысла). Общая логика для обычной заявки
// (useWishApprovers.ts) и карточки-компаньона авансового отчёта
// (useAdvanceReimbursement.ts) — ПРАВИЛО №6, второй расчёт перестановки не заводим.
// Видимость стрелок (approvalMode === 'sequential') — на вызывающей стороне
// (шаблон), backend дополнительно отбивает reorder при parallel 409-м.
export async function moveApprover<A extends CascadeApprover = CascadeApprover>(opts: {
  apiFetch: typeof import('@/api').apiFetch
  wishId: number
  approvers: A[]
  idx: number
  dir: number
  onApprovers: (approvers: A[]) => void
  onError: (message: string) => void
}): Promise<void> {
  const { apiFetch, wishId, approvers, idx, dir, onApprovers, onError } = opts
  const j = idx + dir
  if (j < 0 || j >= approvers.length) return
  const arr: A[] = [...approvers]
  const tmp = arr[idx]!
  arr[idx] = arr[j]!
  arr[j] = tmp
  try {
    const res = await apiFetch<A[]>(
      `/wishes/${wishId}/approvers/reorder`,
      { method: 'POST', body: JSON.stringify({ ids: arr.map(a => a.id) }) },
    )
    onApprovers(res)
  } catch (e: any) {
    onError(e?.payload?.message || e?.message || 'Не удалось изменить порядок согласующих')
  }
}

export type EnsureApproversResult =
  | { ok: true }
  | { ok: false; reason: 'no-top' }
  | { ok: false; reason: 'error'; message: string }

// Перед отправкой: если согласующие уже есть — ничего не делаем (пользователь
// мог добавить их вручную кнопкой «Добавить согласующего», или построить
// цепочку кнопкой «Построить цепочку» — оба пути уже прошли через backend).
// Если согласующих нет, но верхний выбран — добавляем ЕГО ОДНОГО единственным
// согласующим (POST /wishes/{id}/approvers, тот же эндпоинт, что и кнопка
// «Добавить согласующего»; НЕ /approvers/cascade). Если нет ни того, ни
// другого — вызывающая сторона подсвечивает поле «Верхний согласующий»
// (reason: 'no-top').
export async function ensureApproversBeforeSubmit<A extends CascadeApprover = CascadeApprover>(opts: {
  apiFetch: typeof import('@/api').apiFetch
  wishId: number
  currentApproversCount: number
  topUserId: number | null
  onApprovers: (approvers: A[]) => void
}): Promise<EnsureApproversResult> {
  const { apiFetch, wishId, currentApproversCount, topUserId, onApprovers } = opts
  if (currentApproversCount > 0) return { ok: true }
  if (!topUserId) return { ok: false, reason: 'no-top' }
  try {
    await apiFetch(`/wishes/${wishId}/approvers`, {
      method: 'POST', body: JSON.stringify({ user_id: topUserId }),
    })
    const approvers = await apiFetch<A[]>(`/wishes/${wishId}/approvers`)
    onApprovers(approvers)
    return { ok: true }
  } catch (e: any) {
    return { ok: false, reason: 'error', message: e?.payload?.message || e?.message || 'Не удалось добавить согласующего' }
  }
}
