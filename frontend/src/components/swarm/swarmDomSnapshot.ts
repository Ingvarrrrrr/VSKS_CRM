// Снимок живого DOM рабочей области (.v-main) и кэширование реальных экранов GALA.
import { SWARM_AGENTS, type SwarmItem, type SwarmTool, type SwarmVisualKind } from './swarmTypes'

const MAX_SNAPSHOT_ITEMS = 90
const MIN_SNAPSHOT_ITEMS = 2
const DOM_CACHE_KEY = 'gala_swarm_dom_cache_v2'

const memDomCache = new Map<string, SwarmItem[]>()

function routeCacheKey(path: string, isMobile: boolean): string {
  const clean = (path || '/').split('?')[0]
  return `${clean}:${isMobile ? 'm' : 'd'}`
}

export function getCachedRouteSnapshot(path: string, isMobile: boolean): SwarmItem[] | null {
  const key = routeCacheKey(path, isMobile)
  const mem = memDomCache.get(key)
  if (mem && mem.length >= MIN_SNAPSHOT_ITEMS) return mem

  if (typeof window === 'undefined' || !window.sessionStorage) return null
  try {
    const raw = sessionStorage.getItem(DOM_CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    const items = parsed[key] as SwarmItem[] | undefined
    if (items && Array.isArray(items) && items.length >= MIN_SNAPSHOT_ITEMS) {
      memDomCache.set(key, items)
      return items
    }
  } catch {}
  return null
}

export function cacheLiveRouteSnapshot(
  path: string,
  mainEl: HTMLElement | null,
  isDark: boolean,
  isMobile: boolean,
): SwarmItem[] | null {
  const snap = snapshotLiveWorkspace(mainEl, isDark, isMobile)
  if (!snap || snap.length < MIN_SNAPSHOT_ITEMS) return null

  const key = routeCacheKey(path, isMobile)
  memDomCache.set(key, snap)

  if (typeof window !== 'undefined' && window.sessionStorage) {
    try {
      const raw = sessionStorage.getItem(DOM_CACHE_KEY)
      const data = raw ? JSON.parse(raw) : {}
      data[key] = snap
      sessionStorage.setItem(DOM_CACHE_KEY, JSON.stringify(data))
    } catch {}
  }
  return snap
}

function classifyElement(el: HTMLElement): SwarmVisualKind {
  const tag = el.tagName
  if (el.matches('hr, .v-divider')) return 'divider'
  if (el.matches('thead th, .v-data-table__th, thead tr')) return 'table-head'
  if (el.matches('tbody tr, .v-data-table__tr')) return 'table-row'
  if (el.matches('.v-chip, .v-tab')) return 'chip'
  if (el.matches('.v-field')) return 'input'
  if (el.matches('.v-btn')) {
    const cls = el.className || ''
    return cls.includes('bg-primary') || cls.includes('text-white') ? 'btn-primary' : 'btn-outline'
  }
  if (el.matches('h1, h2, h3, .text-h5, .text-h6')) return 'heading'
  if (tag === 'CANVAS' || el.matches('.apexcharts-canvas')) return 'chart'
  if (el.matches('.v-list-item')) return 'tree-row'
  return 'card'
}

function cleanText(raw: string | null | undefined, maxLen = 46): string {
  const s = (raw || '').replace(/\s+/g, ' ').trim()
  return s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s
}

function isUsefulBox(rect: DOMRect, vw: number, vh: number, kind: SwarmVisualKind, el?: HTMLElement): boolean {
  if (el?.matches('.v-data-table-rows-loading, .v-data-table-rows-no-data')) return false
  if (rect.width < 20 || (kind !== 'divider' && rect.height < 14)) return false
  if (rect.bottom < 0 || rect.top > vh || rect.right < 0 || rect.left > vw) return false
  // Отбрасываем гигантские карточки-обёртки во весь экран
  if (kind === 'card' && rect.width > vw * 0.88 && rect.height > vh * 0.55) return false
  return true
}

export function snapshotLiveWorkspace(
  mainEl: HTMLElement | null,
  isDark: boolean,
  isMobile: boolean,
): SwarmItem[] | null {
  if (!mainEl || typeof window === 'undefined') return null
  const mainRect = mainEl.getBoundingClientRect()
  const cs = getComputedStyle(mainEl)
  const pt = parseFloat(cs.paddingTop) || 0
  const pl = parseFloat(cs.paddingLeft) || 0
  const originX = mainRect.left + pl
  const originY = mainRect.top + pt
  const cw = Math.max(300, mainRect.width - pl - (parseFloat(cs.paddingRight) || 0))
  const ch = Math.max(240, mainRect.height - pt - (parseFloat(cs.paddingBottom) || 0))

  const selector = [
    'h1, h2, h3, .text-h5, .text-h6',
    '.v-btn',
    '.v-chip',
    '.v-field',
    '.v-tab',
    '.v-card',
    'thead tr',
    'tbody tr',
    '.v-data-table__tr',
    '.v-list-item',
    'hr, .v-divider',
    '.apexcharts-canvas',
  ].join(', ')

  const candidates = Array.from(mainEl.querySelectorAll<HTMLElement>(selector))
  const collected: Array<{
    rect: DOMRect
    kind: SwarmVisualKind
    el: HTMLElement
    x: number
    y: number
    w: number
    h: number
  }> = []

  const seenBoxes = new Set<string>()
  for (const el of candidates) {
    if (collected.length >= MAX_SNAPSHOT_ITEMS) break
    const style = getComputedStyle(el)
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) < 0.08) continue
    const r = el.getBoundingClientRect()
    const kind = classifyElement(el)
    const relX = Math.round(r.left - originX)
    const relY = Math.round(r.top - originY)
    const relW = Math.round(r.width)
    const relH = kind === 'divider' ? Math.max(2, Math.round(r.height)) : Math.round(r.height)
    const relRect = new DOMRect(relX, relY, relW, relH)
    if (!isUsefulBox(relRect, cw, ch, kind, el)) continue

    const sig = `${Math.round(relX / 8)}:${Math.round(relY / 8)}:${Math.round(relW / 12)}:${Math.round(relH / 8)}`
    if (seenBoxes.has(sig)) continue
    seenBoxes.add(sig)
    collected.push({ rect: relRect, kind, el, x: relX, y: relY, w: relW, h: relH })
  }

  if (collected.length < MIN_SNAPSHOT_ITEMS) return null
  collected.sort((a, b) => (Math.abs(a.y - b.y) > 16 ? a.y - b.y : a.x - b.x))

  const agentLimit = isMobile ? 3 : SWARM_AGENTS.length
  const firstOfShape = new Map<string, string>()
  const result: SwarmItem[] = []

  collected.forEach((entry, idx) => {
    const { el, kind, x, y, w, h } = entry
    const id = `live-${idx}`
    const style = getComputedStyle(el)
    const shapeKey = `${kind}:${Math.round(w / 14)}:${Math.round(h / 10)}`
    const prevId = firstOfShape.get(shapeKey)

    let tool: SwarmTool = 'rect'
    let dupFromId: string | undefined
    if (kind === 'divider' || kind === 'chart') {
      tool = 'pen'
    } else if (kind === 'heading') {
      tool = 'type'
    } else if (prevId && (kind === 'chip' || kind === 'table-row' || kind === 'btn-outline' || kind === 'tree-row' || kind === 'card')) {
      tool = 'dup'
      dupFromId = prevId
    } else if (!prevId) {
      firstOfShape.set(shapeKey, id)
    }

    let cells: string[] | undefined
    let text = cleanText(el.innerText)
    let subtext: string | undefined
    let statusText: string | undefined

    if (kind === 'table-row' || kind === 'table-head') {
      const cellEls = Array.from(el.querySelectorAll<HTMLElement>('td, th')).slice(0, 10)
      if (cellEls.length) {
        cells = cellEls.map((c) => cleanText(c.innerText, 28) || '—')
        text = cells[0]
      }
    } else if (kind === 'card') {
      const lines = (el.innerText || '').split('\n').map((l) => l.trim()).filter(Boolean)
      if (lines.length >= 1) text = cleanText(lines[0], 34)
      if (lines.length >= 2) subtext = cleanText(lines[1], 34)
      const badge = el.querySelector<HTMLElement>('.v-chip, .v-badge, [class*="status"]')
      if (badge) statusText = cleanText(badge.innerText, 16)
    }

    const startMs = Math.min(2050, 20 + Math.round((idx / collected.length) * 1850))
    const durationMs = kind === 'divider' ? 260 : kind === 'table-row' || kind === 'chip' ? 300 : 400

    result.push({
      id,
      kind,
      tool,
      x: Math.max(8, x),
      y: Math.max(8, y),
      w: Math.min(cw - 16, w),
      h: Math.min(ch - 16, h),
      rx: Math.min(14, parseFloat(style.borderRadius) || (kind === 'chip' ? 999 : 8)),
      dupFromId,
      text: text || (kind === 'input' ? 'Поиск…' : undefined),
      subtext,
      statusText,
      cells,
      bg: style.backgroundColor && style.backgroundColor !== 'rgba(0, 0, 0, 0)' ? style.backgroundColor : undefined,
      border: style.borderColor,
      color: style.color,
      accent: kind === 'btn-primary',
      cursorIndex: idx % agentLimit,
      startMs,
      durationMs,
      el,
    })
  })

  return result
}
