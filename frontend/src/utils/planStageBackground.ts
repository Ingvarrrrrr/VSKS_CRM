/**
 * Фон строки плановой позиции/категории дерева ФЭО по стадии закупки
 * (владелец, 16.10.2026) — ЕДИНСТВЕННАЯ функция сборки CSS из stage_segments
 * (см. backend/app/services/plan_item_stage.py), используют FeoLevel5Panel.vue
 * (строка плановой позиции) и FeoTreeRow.vue (строка категории, сегменты
 * агрегированы usePlanToRequest.ts::categoryStageSegments). ПРАВИЛО №6: второй
 * способ раскраски (штриховка/«пузырьки» styles/subsidies.css) убран —
 * заменён этим фоном везде.
 *
 * «Полосы друг над другом по высоте строки, каждая на всю длину; сверху самая
 * дальняя стадия, ниже более ранние; недокупленное — пустое снизу» (владелец).
 * segments[] приходит С БЭКА уже отсортированным от самой дальней стадии к
 * самой ранней (см. _STAGE_RANK/_build_segments) — здесь порядок не меняем,
 * только переводим share в % высоты и строим жёсткие границы (без растушёвки).
 */
import { planStageColor, planStageLabel } from '@/constants/planStageScale'

export interface PlanStageSegment {
  purchase_id: number
  registry_number: string | null
  stage: string
  share: number
  quantity: number
  amount: number
}

/** segments[] (уже в порядке «сверху вниз» от дальней стадии к ранней) → CSS
 *  background: linear-gradient с жёсткими границами, остаток снизу —
 *  прозрачный (пустая строка видна как обычный фон строки). */
export function planStageBackground(segments: PlanStageSegment[] | null | undefined): string | null {
  if (!segments || segments.length === 0) return null
  const stops: string[] = []
  let cursor = 0
  for (const seg of segments) {
    const share = Math.max(0, Math.min(1, Number(seg.share) || 0))
    if (share <= 0) continue
    const from = cursor
    const to = Math.min(100, cursor + share * 100)
    const color = planStageColor(seg.stage)
    stops.push(`${color} ${from}%`, `${color} ${to}%`)
    cursor = to
  }
  if (!stops.length) return null
  if (cursor < 100) {
    stops.push('transparent ' + cursor + '%', 'transparent 100%')
  }
  return `linear-gradient(to bottom, ${stops.join(', ')})`
}

/** Подсказка при наведении на строку — «РЕЕ-… · Поставлено · 100 шт (50 %)» по
 *  каждой полосе (владелец). unit — единица измерения позиции (для подписи
 *  количества), amount используется, когда unit/quantity не заданы. */
export function planStageTooltip(segments: PlanStageSegment[] | null | undefined, unit?: string | null): string {
  if (!segments || segments.length === 0) return ''
  return segments
    .map((seg) => {
      const pct = Math.round((Number(seg.share) || 0) * 1000) / 10
      const numberLabel = seg.registry_number || `закупка №${seg.purchase_id}`
      const qtyLabel = seg.quantity > 0
        ? `${formatQty(seg.quantity)}${unit ? ' ' + unit : ' шт'}`
        : `${formatQty(seg.amount)} ₽`
      return `${numberLabel} · ${planStageLabel(seg.stage)} · ${qtyLabel} (${formatQty(pct)}%)`
    })
    .join('\n')
}

function formatQty(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '')
}
