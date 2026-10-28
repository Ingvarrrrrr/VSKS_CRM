// Единый список кодов «нужно решить перед формированием документа» — НЕ
// ошибка/баг, а предсказуемый отказ 409/422, пока человек не принял решение,
// которое система не вправе придумать сама (дубли ТЗ, ставка НДС, способ
// закупки, пустой список позиций договора). Владелец (28.10.2026, карточка
// закупки): TZ_DUPLICATES_UNRESOLVED фронт показывал как красную «Ошибку
// генерации документа» с «Скопировать ошибку» — это не ошибка, а обычное
// сообщение, которое должно вести стрелкой к месту решения.
//
// ПРАВИЛО №6: один список, а не разбросанные по компонентам проверки вида
// `code === 'TZ_DUPLICATES_UNRESOLVED' || code === '...'`. DocErrorDialog.vue —
// единственное место, которое его читает, чтобы решить: красный диалог
// ошибки или информационное сообщение без кнопки «Скопировать ошибку».
//
// Источник кодов — backend/app/services/documents/{contexts.py,templates.py}
// (см. HTTPException(detail={"code": ...})).
export const ACTION_REQUIRED_DOC_CODES = new Set<string>([
  'TZ_DUPLICATES_UNRESOLVED',
  'CONTRACT_ITEMS_REQUIRED',
  'VAT_RATE_REQUIRED',
  'VAT_EXEMPTION_ARTICLE_REQUIRED',
  'PURCHASE_METHOD_REQUIRED',
])

export function isActionRequiredDocCode(code: string | null | undefined): boolean {
  return !!code && ACTION_REQUIRED_DOC_CODES.has(code)
}
