import { computed, type Ref } from 'vue'
import type { OdometerRow, Checklist, FieldHistoryItem, TransferHistoryItem, TimelineEvent } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Лента событий карточки ТС (Slice-2) — объединяет 4 источника (пробег,
// последний чек-лист, история полей, история передач) в единый список,
// отсортированный по дате, последние 8.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleTimeline(
  odometerRows: Ref<OdometerRow[]>,
  lastChecklist: Ref<Checklist | null>,
  fieldHistory: Ref<FieldHistoryItem[]>,
  transferHistory: Ref<TransferHistoryItem[]>,
) {
  const timelineEvents = computed((): TimelineEvent[] => {
    const events: TimelineEvent[] = []

    // Odometer rows
    for (const r of odometerRows.value) {
      const prev = odometerRows.value.find(x => x.id !== r.id && new Date(x.date) < new Date(r.date))
      const delta = r.delta_km != null ? r.delta_km : (prev ? r.odometer_km - prev.odometer_km : null)
      events.push({
        date: r.date,
        dotClass: 'info',
        title: `Пробег: ${r.odometer_km.toLocaleString('ru-RU')} км${delta != null ? ` (+${delta.toLocaleString('ru-RU')})` : ''}`,
        body: r.note ?? undefined,
      })
    }

    // Checklists (only last checklist in widget data - we loaded just the last one)
    if (lastChecklist.value) {
      const cl = lastChecklist.value
      const isWarn = cl.overall_state === 'with_remarks' || cl.overall_state === 'not_running'
      events.push({
        date: cl.created_at,
        dotClass: isWarn ? 'warn' : 'ok',
        title: isWarn ? 'Чек-лист с замечаниями' : 'Чек-лист пройден',
        body: cl.notes ?? undefined,
      })
    }

    // Field history
    for (const h of fieldHistory.value) {
      events.push({
        date: h.changed_at,
        dotClass: 'info',
        title: `Изменено: ${h.field_key}`,
        body: h.comment ?? undefined,
      })
    }

    // Transfer history
    for (const t of transferHistory.value) {
      events.push({
        date: t.changed_at,
        dotClass: 'info',
        title: 'Передача ТС',
        body: [t.from_assigned_text, t.to_assigned_text].filter(Boolean).join(' → ') || undefined,
      })
    }

    return events
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      .slice(0, 8)
  })

  return { timelineEvents }
}
