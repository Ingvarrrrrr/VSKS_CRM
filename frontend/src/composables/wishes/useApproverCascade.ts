// useApproverCascade.ts — ОДИН источник истины для вызова POST /wishes/{id}/
// approvers/cascade и для правила «нет согласующих, но выбран верхний —
// перед отправкой построить цепочку автоматически» (ПРАВИЛО №6: раньше этот
// POST-вызов и решение "что делать, если approvers пуст" были продублированы
// в useWishApprovers.ts (обычная заявка) и useAdvanceReimbursement.ts
// (заявка-компаньон авансового отчёта) — теперь оба зовут отсюда).
//
// Владелец (прод, заявка №85, 2026-09-29): выбрал верхнего согласующего, НЕ
// нажал «Построить цепочку», нажал «Отправить на согласование» → бэк отклонил
// (approvers пуст). Вопрос владельца: «автоматическое сохранение почему не
// происходит?» — значит на «Отправить» нужно САМИМ вызвать ту же цепочку
// (эндпоинт и режим те же, что у кнопки «Построить цепочку»), а не только
// добавлять одного человека (это и было прежним, более слабым поведением
// useWishApprovers.ensureApprovers — оно ставило верхнего единственным
// согласующим без восходящей цепочки).
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

export type EnsureApproversResult =
  | { ok: true; warning?: string | null }
  | { ok: false; reason: 'no-top' }
  | { ok: false; reason: 'error'; message: string }

// Перед отправкой: если согласующие уже есть — ничего не делаем (пользователь
// мог добавить их вручную кнопкой «Добавить согласующего», без цепочки).
// Если согласующих нет, но верхний выбран — строим цепочку тем же вызовом,
// что и кнопка «Построить цепочку». Если нет ни того, ни другого — вызывающая
// сторона подсвечивает поле «Верхний согласующий» (reason: 'no-top').
export async function ensureApproversBeforeSubmit<A extends CascadeApprover = CascadeApprover>(opts: {
  apiFetch: typeof import('@/api').apiFetch
  wishId: number
  currentApproversCount: number
  topUserId: number | null
  mode: 'sequential' | 'parallel'
  onApprovers: (approvers: A[]) => void
}): Promise<EnsureApproversResult> {
  const { apiFetch, wishId, currentApproversCount, topUserId, mode, onApprovers } = opts
  if (currentApproversCount > 0) return { ok: true }
  if (!topUserId) return { ok: false, reason: 'no-top' }
  try {
    const res = await callApproverCascade<A>(apiFetch, wishId, topUserId, mode)
    onApprovers(res.approvers)
    return { ok: true, warning: res.warning }
  } catch (e: any) {
    return { ok: false, reason: 'error', message: e?.payload?.message || e?.message || 'Не удалось построить цепочку согласующих' }
  }
}
