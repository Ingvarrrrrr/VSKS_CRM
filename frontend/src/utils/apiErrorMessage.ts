// Единая распаковка ошибки apiFetch (api.ts) для snackbar-сообщений — не
// глотать причину generic-текстом (память проекта
// feedback_no_generic_error_snackbar). apiFetch кладёт человекочитаемое
// сообщение в err.payload.message (и дублирует в err.detail) + HTTP-статус в
// err.status — этот хелпер собирает их в одну строку. Один источник этой
// логики (ПРАВИЛО №6): используется и в useItemsCatalog.ts (диалог полной
// карточки товара), и в useProductsForm.ts (диалог "Редактировать товар" в
// каталоге) — не копировать по каждому catch.
export function describeApiError(
  err: any,
  opts?: { fallback?: string; prefix?: string },
): string {
  const fallback = opts?.fallback ?? 'Не удалось выполнить запрос'
  const prefix = opts?.prefix ?? 'Ошибка'
  const rawMsg = err?.payload?.message ?? err?.detail ?? err?.message
  const msg = typeof rawMsg === 'string' && rawMsg.trim() ? rawMsg : fallback
  const status = err?.status
  return status ? `${prefix} (${status}): ${msg}` : `${prefix}: ${msg}`
}
