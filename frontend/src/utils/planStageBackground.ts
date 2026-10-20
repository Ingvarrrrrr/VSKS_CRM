/**
 * Фон строки плановой позиции/категории дерева ФЭО по стадии закупки
 * (владелец, 20.10.2026) — ЕДИНСТВЕННАЯ функция сборки CSS из stage_segments
 * (см. backend/app/services/plan_item_stage.py), используют FeoLevel5Panel.vue
 * (строка плановой позиции) и FeoTreeRow.vue (строка категории, сегменты
 * агрегированы usePlanToRequest.ts::categoryStageSegments). ПРАВИЛО №6: второй
 * способ раскраски (штриховка/«пузырьки» styles/subsidies.css) убран —
 * заменён этим фоном везде.
 *
 * Схема (владелец, 20.10.2026): плашка строки разбита по ГОРИЗОНТАЛИ на 5
 * отрезков — по числу стадий шкалы STAGE_ORDER (в работе/договор/заказано/
 * оплачено по отметке/подтверждено выпиской). Ширина закраски сегмента =
 * номер его стадии в шкале (rank, 1..5) из пяти отрезков слева направо;
 * неизвестная стадия — rank 5 (вся ширина), цветом planStageColor('плохой
 * ключ') = серый «закуплено полностью». Высота сегмента, как и раньше, — доля
 * количества (share), сегменты идут сверху вниз в порядке, в котором пришли
 * с бэка (от самой дальней стадии к самой ранней), недокупленное — пустое
 * снизу. Между отрезками — тонкие вертикальные разделители на 20/40/60/80%,
 * чтобы было видно границы стадий даже на одноцветной полосе.
 */
import { planStageColor, planStageLabel, STAGE_ORDER, type PlanStageKey } from '@/constants/planStageScale'

export interface PlanStageSegment {
  purchase_id: number
  registry_number: string | null
  stage: string
  share: number
  quantity: number
  amount: number
}

export interface PlanStageStyle {
  backgroundImage: string
  backgroundSize: string
  backgroundPosition: string
  backgroundRepeat: string
}

const SEPARATOR_COLOR = 'rgba(0, 0, 0, 0.12)'
const SEPARATOR_IMAGE = `linear-gradient(to right, ${[20, 40, 60, 80]
  .map((p) => `transparent calc(${p}% - 1px), ${SEPARATOR_COLOR} calc(${p}% - 1px), ${SEPARATOR_COLOR} ${p}%, transparent ${p}%`)
  .join(', ')})`

function stageRank(stage: string): number {
  const idx = STAGE_ORDER.indexOf(stage as PlanStageKey)
  return idx >= 0 ? idx + 1 : STAGE_ORDER.length
}

/** segments[] (уже в порядке «сверху вниз» от дальней стадии к ранней) → набор
 *  CSS-слоёв background: разделители (сверху, во всю строку) + по одному
 *  linear-gradient-слою на сегмент (ширина — отрезки стадии, высота — доля
 *  количества, прижат в левый верхний угол своей вертикальной позиции). */
export function planStageBackground(segments: PlanStageSegment[] | null | undefined): PlanStageStyle | null {
  if (!segments || segments.length === 0) return null
  const images: string[] = []
  const sizes: string[] = []
  const positions: string[] = []
  let cursor = 0
  let any = false
  for (const seg of segments) {
    const share = Math.max(0, Math.min(1, Number(seg.share) || 0))
    if (share <= 0) continue
    const heightPct = Math.min(100, share * 100)
    const topPct = heightPct >= 100 ? 0 : (cursor / (100 - heightPct)) * 100
    const widthPct = (stageRank(seg.stage) / STAGE_ORDER.length) * 100
    const color = planStageColor(seg.stage)
    images.push(`linear-gradient(${color}, ${color})`)
    sizes.push(`${widthPct}% ${heightPct}%`)
    positions.push(`0% ${topPct}%`)
    cursor = Math.min(100, cursor + heightPct)
    any = true
  }
  if (!any) return null
  images.unshift(SEPARATOR_IMAGE)
  sizes.unshift('100% 100%')
  positions.unshift('0 0')
  return {
    backgroundImage: images.join(', '),
    backgroundSize: sizes.join(', '),
    backgroundPosition: positions.join(', '),
    backgroundRepeat: images.map(() => 'no-repeat').join(', '),
  }
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
