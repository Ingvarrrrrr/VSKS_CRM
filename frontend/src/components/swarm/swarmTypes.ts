// Типы высокоплотных чертёжных примитивов и палитра курсоров GALA
// для визуализации сборки экрана (Swarm Rebuild v2).

export type SwarmTool = 'rect' | 'type' | 'dup' | 'pen'

export type SwarmVisualKind =
  | 'card'
  | 'btn-primary'
  | 'btn-outline'
  | 'input'
  | 'chip'
  | 'heading'
  | 'tree-row'
  | 'table-head'
  | 'table-row'
  | 'kpi'
  | 'divider'
  | 'chart'
  | 'step'

export type SwarmBlueprintKind =
  | 'boot'
  | 'subsidies'
  | 'registry'
  | 'form'
  | 'dashboard'
  | 'tasks'

export interface SwarmAgent {
  id: string
  name: string
  colorLight: string
  colorDark: string
}

export interface SwarmItem {
  id: string
  kind: SwarmVisualKind
  tool: SwarmTool
  /** Координаты в пикселях относительно холста (для точных линеек, сетки и дубликатов) */
  x: number
  y: number
  w: number
  h: number
  rx?: number
  dupFromId?: string
  text?: string
  subtext?: string
  rightText?: string
  statusText?: string
  statusColor?: string
  cells?: string[]
  bg?: string
  border?: string
  color?: string
  accent?: boolean
  cursorIndex: number
  startMs: number
  durationMs: number
  el?: HTMLElement
}

export interface SwarmGuide {
  id: string
  axis: 'x' | 'y'
  pos: number
  label: string
  color: string
}

export interface SwarmBlueprint {
  kind: SwarmBlueprintKind
  screenTitle: string
  items: SwarmItem[]
  columns: string[]
}

export const SWARM_AGENTS: SwarmAgent[] = [
  { id: 'feo', name: 'ФЭО', colorLight: '#c2620a', colorDark: '#fb923c' },
  { id: 'orders', name: 'Закупки', colorLight: '#2563eb', colorDark: '#60a5fa' },
  { id: 'contracts', name: 'Договоры', colorLight: '#16a34a', colorDark: '#4ade80' },
  { id: 'treasury', name: 'Казначейство', colorLight: '#d97706', colorDark: '#fbbf24' },
  { id: 'warehouse', name: 'Склад', colorLight: '#7c3aed', colorDark: '#a78bfa' },
  { id: 'control', name: 'Контроль', colorLight: '#0d9488', colorDark: '#2dd4bf' },
]
