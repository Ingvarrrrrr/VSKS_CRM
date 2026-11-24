import { apiFetch } from '@/api'
import type { GalaCellContextOptions, CellHistoryEvent } from '@/composables/useGalaContextMenu'
import { formatFeoHistoryValue } from '@/constants/feoHistoryValueFormat'

export const AVATAR_COLORS = [
  '#10B981', '#3B82F6', '#8B5CF6', '#EC4899',
  '#F59E0B', '#06B6D4', '#6366F1', '#14B8A6',
]

export function avatarColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash << 5) - hash + name.charCodeAt(i)
    hash |= 0
  }
  const idx = Math.abs(hash) % AVATAR_COLORS.length
  return AVATAR_COLORS[idx] || '#10B981'
}

export function avatarLetter(name: string): string {
  const trimmed = (name || '').trim()
  return trimmed ? trimmed.charAt(0).toUpperCase() : 'С'
}

export function formatRussianDate(d: string | Date | undefined): string {
  if (!d) return ''
  try {
    const date = typeof d === 'string' ? new Date(d) : d
    const now = new Date()
    const isCurrentYear = date.getFullYear() === now.getFullYear()
    return date.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit',
      year: isCurrentYear ? undefined : 'numeric',
    })
  } catch {
    return String(d)
  }
}

export function formatCellValue(raw: any, options?: GalaCellContextOptions | null): string {
  if (raw === null || raw === undefined || raw === '' || raw === 'None') return '—'
  if (raw === true || raw === 'true') return 'Да'
  if (raw === false || raw === 'false') return 'Нет'

  if (options && (options.entityType === 'feo_item' || options.entityType === 'feo_category')) {
    return formatFeoHistoryValue(options.fieldName, String(raw))
  }

  if (typeof raw === 'number' || (!isNaN(Number(raw)) && /^-?\d+(\.\d+)?$/.test(String(raw).trim()))) {
    const num = Number(raw)
    if (Number.isFinite(num)) {
      return num.toLocaleString('ru-RU')
    }
  }

  return String(raw)
}

export async function fetchCellHistory(opts: GalaCellContextOptions): Promise<CellHistoryEvent[]> {
  if (opts.historyLoader) {
    return await opts.historyLoader(opts)
  }

  // Расчётные, сводные строки или строки без реального ID
  if (!opts.entityType || opts.entityType === 'table_row' || Number(opts.entityId) <= 0) {
    return [
      {
        id: 'calc',
        changedAt: '',
        changedByName: 'Система GALA',
        oldValue: null,
        newValue: opts.cellValue,
        isCreated: true,
        isCalculatedOrEmpty: true,
        originLabel: 'Расчётная или сводная ячейка (формируется автоматически, вручную не редактировалась)',
      },
    ]
  }

  if (opts.entityType === 'vehicle') {
    const url = `/vehicles/${opts.entityId}/field-history?field_key=${encodeURIComponent(opts.fieldName)}&limit=50`
    const raw = await apiFetch<any[]>(url)
    const list = Array.isArray(raw) ? raw : []
    return list.map((r, i) => ({
      id: r.id || i,
      changedAt: r.changed_at,
      changedByName: r.changed_by_name || (r.changed_by_user_id ? `Пользователь #${r.changed_by_user_id}` : null),
      oldValue: r.old_value,
      newValue: r.new_value,
      comment: r.comment,
    }))
  }

  // Default /entity-changes
  const url = `/entity-changes/${opts.entityType}/${opts.entityId}`
  const raw = await apiFetch<any[]>(url)
  const list = Array.isArray(raw) ? raw : []

  const fieldChanges = list.filter(c => c.field_name === opts.fieldName)
  const created = list.find(c => c.field_name === '__created__')

  if (fieldChanges.length > 0) {
    const mapped: CellHistoryEvent[] = fieldChanges.map((c, i) => ({
      id: c.id || i,
      changedAt: c.changed_at,
      changedByName: c.changed_by_name,
      oldValue: c.old_value,
      newValue: c.new_value,
      source: c.source,
      comment: c.comment,
      originLabel: c.origin_label,
    }))

    if (created) {
      mapped.push({
        id: created.id ?? 'origin',
        changedAt: created.changed_at,
        changedByName: created.changed_by_name,
        oldValue: null,
        newValue: fieldChanges[fieldChanges.length - 1].old_value ?? opts.cellValue,
        isCreated: true,
        source: created.source,
        originLabel: created.origin_label,
      })
    }

    return mapped
  }

  if (created) {
    return [
      {
        id: created.id ?? 'origin',
        changedAt: created.changed_at,
        changedByName: created.changed_by_name,
        oldValue: null,
        newValue: opts.cellValue,
        isCreated: true,
        source: created.source,
        originLabel: created.origin_label,
        comment: 'После внесения эта ячейка отдельно не изменялась',
      },
    ]
  }

  return []
}
