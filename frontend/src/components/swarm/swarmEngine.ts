// Покадровый движок вычисления размеров, направляющих, дубликатов ⌥
// и целей курсоров (Swarm Rebuild v2).

import { SWARM_AGENTS, type SwarmGuide, type SwarmItem, type SwarmTool } from './swarmTypes'

export interface RulerTick {
  pos: number
  major: boolean
  label?: string
}

export interface DupVector {
  x1: number
  y1: number
  x2: number
  y2: number
  distLabel: string
}

export interface RenderedSwarmItem extends SwarmItem {
  curX: number
  curY: number
  curW: number
  curH: number
  dragProgress: number
  detailProgress: number
  snapped: boolean
  showContent: boolean
  showHandles: boolean
  typedText: string
  isTyping: boolean
  sizeHint: string
  dupVector?: DupVector
  boxStyle: {
    transform: string
    width: string
    height: string
    borderRadius: string
  }
}

export interface TargetSwarmCursor {
  id: string
  name: string
  color: string
  rawX: number
  rawY: number
  opacity: number
  activeTool: SwarmTool
}

export function easeOutCubic(t: number): number {
  const c = Math.max(0, Math.min(1, t))
  return 1 - Math.pow(1 - c, 3)
}

export function computeRulerTicks(width: number, height: number) {
  const xTicks: RulerTick[] = []
  const yTicks: RulerTick[] = []
  for (let x = 0; x <= width; x += 50) {
    const major = x % 100 === 0
    xTicks.push({ pos: x, major, label: major ? String(x) : undefined })
  }
  for (let y = 0; y <= height; y += 50) {
    const major = y % 100 === 0
    yTicks.push({ pos: y, major, label: major ? String(y) : undefined })
  }
  return { xTicks, yTicks }
}

export function computeActiveGuides(items: RenderedSwarmItem[], isDark: boolean): SwarmGuide[] {
  const active = items.filter((i) => !i.snapped && i.dragProgress > 0.05)
  const guides: SwarmGuide[] = []
  const color = isDark ? 'rgba(251, 146, 60, 0.55)' : 'rgba(194, 98, 10, 0.52)'
  for (const item of active.slice(0, 2)) {
    guides.push({ id: `gx-${item.id}`, axis: 'x', pos: Math.round(item.curY), label: `Y:${Math.round(item.curY)}`, color })
    guides.push({ id: `gy-${item.id}`, axis: 'y', pos: Math.round(item.curX), label: `X:${Math.round(item.curX)}`, color })
  }
  return guides
}

export function computeRenderedItems(
  items: SwarmItem[],
  el: number,
  completing: boolean,
  snappedIds: Set<string>,
  onSnap: (idx: number) => void,
): RenderedSwarmItem[] {
  const byId = new Map(items.map((it) => [it.id, it]))

  return items
    .map((item, idx) => {
      const local = (el - item.startMs) / item.durationMs
      if (local <= 0 && !completing) return null

      const p = completing ? 1 : Math.min(1, Math.max(0.02, local))
      const dragProgress = completing ? 1 : easeOutCubic(Math.min(1, p / 0.62))
      const typeProgress = completing ? 1 : Math.max(0, Math.min(1, (p - 0.45) / 0.5))
      const detailProgress = completing ? 1 : Math.max(0, Math.min(1, (p - 0.52) / 0.48))
      const snapped = completing || p >= 0.98

      if (snapped && !snappedIds.has(item.id) && !completing) {
        snappedIds.add(item.id)
        if (idx % 4 === 0) onSnap(idx)
      }

      let curX = item.x
      let curY = item.y
      let curW = item.w
      let curH = item.h
      let dupVector: DupVector | undefined

      const src = item.dupFromId ? byId.get(item.dupFromId) : undefined
      if (item.tool === 'dup' && src && !completing && dragProgress < 0.99) {
        curX = src.x + (item.x - src.x) * dragProgress
        curY = src.y + (item.y - src.y) * dragProgress
        const dist = Math.round(Math.hypot(item.x - src.x, item.y - src.y))
        dupVector = {
          x1: Math.round(src.x + src.w * 0.5),
          y1: Math.round(src.y + src.h * 0.5),
          x2: Math.round(curX + curW * 0.5),
          y2: Math.round(curY + curH * 0.5),
          distLabel: `⌥ +${dist}px`,
        }
      } else if (item.tool === 'pen') {
        curW = Math.max(12, item.w * (item.kind === 'chart' ? 1 : dragProgress))
      } else if (item.tool === 'rect') {
        curW = Math.max(16, item.w * (0.14 + 0.86 * dragProgress))
        curH = Math.max(14, item.h * (0.18 + 0.82 * dragProgress))
      }

      const rawText = item.text || ''
      const typedLen = Math.round(rawText.length * typeProgress)

      return {
        ...item,
        curX,
        curY,
        curW,
        curH,
        dragProgress,
        detailProgress,
        snapped,
        showContent: item.tool === 'dup' || item.tool === 'type' || dragProgress > 0.42,
        showHandles: !snapped && dragProgress > 0.14,
        typedText: rawText.slice(0, typedLen),
        isTyping: rawText.length > 0 && typeProgress > 0.05 && typeProgress < 1 && !snapped,
        sizeHint: `${Math.round(curW)} × ${Math.round(curH)}`,
        dupVector,
        boxStyle: {
          transform: `translate3d(${Math.round(curX)}px, ${Math.round(curY)}px, 0)`,
          width: `${Math.round(curW)}px`,
          height: `${Math.round(curH)}px`,
          borderRadius: `${item.rx ?? 8}px`,
        },
      }
    })
    .filter((v): v is RenderedSwarmItem => v !== null)
}

export function computeCursorTarget(item: SwarmItem, el: number, itemsById: Map<string, SwarmItem>) {
  const p = Math.max(0, Math.min(1, (el - item.startMs) / item.durationMs))
  const src = item.dupFromId ? itemsById.get(item.dupFromId) : undefined

  if (item.tool === 'dup' && src) {
    const dp = easeOutCubic(Math.min(1, p / 0.62))
    const x = src.x + (item.x - src.x) * dp + item.w * 0.5
    const y = src.y + (item.y - src.y) * dp + item.h * 0.5
    return { x, y, tool: 'dup' as SwarmTool }
  }
  if (p < 0.15) return { x: item.x, y: item.y, tool: item.tool }
  if (p < 0.64) {
    const dp = easeOutCubic((p - 0.15) / 0.49)
    return {
      x: item.x + item.w * (0.14 + 0.86 * dp),
      y: item.y + (item.kind === 'divider' ? 0 : item.h * (0.18 + 0.82 * dp)),
      tool: item.tool,
    }
  }
  const tp = Math.min(1, (p - 0.64) / 0.36)
  const textLen = (item.text || '').length || 12
  return {
    x: item.x + 12 + Math.min(item.w - 20, textLen * 7.1 * tp),
    y: item.y + Math.min(18, item.h * 0.5),
    tool: item.text ? ('type' as SwarmTool) : item.tool,
  }
}

export function computeTargetCursors(
  items: SwarmItem[],
  el: number,
  cw: number,
  ch: number,
  isMobile: boolean,
  isDark: boolean,
  completing: boolean,
): TargetSwarmCursor[] {
  const limit = isMobile ? 3 : SWARM_AGENTS.length
  const itemsById = new Map(items.map((it) => [it.id, it]))
  const maxEnd = items.reduce((acc, it) => Math.max(acc, it.startMs + it.durationMs), 1000)

  return SWARM_AGENTS.slice(0, limit).map((agent, idx) => {
    const owned = items.filter((b) => b.cursorIndex === idx)
    const targetItem =
      owned.find((b) => el < b.startMs + b.durationMs) || owned[owned.length - 1] || items[idx % items.length]
    const allDone = el >= maxEnd

    let pt = { x: (cw * (idx + 1)) / (limit + 1), y: ch * 0.25, tool: 'rect' as SwarmTool }
    let opacity = 1

    if (targetItem) {
      if (allDone && !completing) {
        const hoverStep = Math.floor((el - maxEnd) / 620)
        const tableRows = items.filter((it) => it.kind === 'table-row' || it.kind === 'tree-row')
        if (idx === hoverStep % limit && tableRows.length > 0) {
          const row = tableRows[hoverStep % tableRows.length]
          pt = { x: row.x + Math.min(row.w * 0.65, 180 + idx * 45), y: row.y + row.h * 0.5, tool: 'type' }
        } else {
          pt = computeCursorTarget(targetItem, targetItem.startMs + targetItem.durationMs, itemsById)
          opacity = 0.36
        }
      } else {
        pt = computeCursorTarget(targetItem, el, itemsById)
      }
    }

    return {
      id: agent.id,
      name: agent.name,
      color: isDark ? agent.colorDark : agent.colorLight,
      rawX: pt.x,
      rawY: pt.y,
      opacity,
      activeTool: pt.tool,
    }
  })
}
