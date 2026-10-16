/**
 * Шкала стадий закупки для раскраски плановых позиций дерева ФЭО (владелец,
 * 16.10.2026): «цветом будет отображаться стадия, а заполнение строки этим
 * цветом — какое количество уже закуплено». ЕДИНСТВЕННЫЙ источник порядка/
 * подписи/цвета этой шкалы — читают frontend/src/utils/planStageBackground.ts,
 * FeoLevel5Panel.vue, FeoTreeRow.vue, FeoTreeToolbar.vue (легенда).
 *
 * ПРАВИЛО №6: это НЕ дубликат constants/purchaseStatus.ts (словарь статусов
 * закупки, 7 значений 1:1 с Purchase.status) — здесь 5 шагов, два статуса
 * ('plan_schedule'+'work_in_progress' и 'ordered'+'delivered') объединены в
 * один шаг каждый, а два шага ('paid_marked'/'paid_confirmed') вообще не
 * статусы закупки, а производная величина (оплата по позиции, см. backend
 * app.services.plan_item_stage._resolve_stage). Переиспользовать
 * PURCHASE_STATUS_META для этой шкалы нельзя — разная арность и разный смысл
 * последнего шага ('paid' status ↛ 'paid_confirmed' stage напрямую).
 *
 * Ключи STAGE_KEY — ТЕ ЖЕ строки, что отдаёт backend в
 * stage_segments[].stage (GET /feo-categories/plan-positions, см.
 * backend/app/services/plan_item_stage.py STAGE_*).
 */

export type PlanStageKey = 'in_work' | 'contracted' | 'ordered' | 'paid_marked' | 'paid_confirmed'

export interface PlanStageMeta {
  key: PlanStageKey
  label: string
  /** Цвет полосы — светлый/полупрозрачный, чтобы текст строки оставался читаемым. */
  color: string
}

/** Порядок ОТ РАННЕЙ К ПОЗДНЕЙ стадии — используется легендой (слева→направо)
 *  и подписью чипа «Закуплено полностью». Для самой полосы (сверху — самая
 *  дальняя стадия) см. STAGE_ORDER.slice().reverse() в planStageBackground.ts. */
export const STAGE_ORDER: PlanStageKey[] = ['in_work', 'contracted', 'ordered', 'paid_marked', 'paid_confirmed']

export const PLAN_STAGE_META: Record<PlanStageKey, PlanStageMeta> = {
  in_work: { key: 'in_work', label: 'В работе', color: 'rgba(253, 230, 138, 0.55)' },
  contracted: { key: 'contracted', label: 'Договор', color: 'rgba(250, 204, 21, 0.55)' },
  ordered: { key: 'ordered', label: 'Заказано / поставлено', color: 'rgba(190, 220, 100, 0.55)' },
  paid_marked: { key: 'paid_marked', label: 'Оплачено по отметке', color: 'rgba(167, 243, 208, 0.65)' },
  paid_confirmed: { key: 'paid_confirmed', label: 'Подтверждено выпиской', color: 'rgba(74, 222, 128, 0.65)' },
}

export function planStageLabel(stage: string | null | undefined): string {
  return (stage && PLAN_STAGE_META[stage as PlanStageKey]?.label) || 'Закуплено полностью'
}

export function planStageColor(stage: string | null | undefined): string {
  return (stage && PLAN_STAGE_META[stage as PlanStageKey]?.color) || 'rgba(148, 163, 184, 0.5)'
}
