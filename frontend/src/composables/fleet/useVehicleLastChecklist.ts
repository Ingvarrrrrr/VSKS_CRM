import { ref } from 'vue'
import { apiFetch } from '@/api'
import type { Checklist, ChecklistItem } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Последний чек-лист водителя для карточки ТС (Slice-2 widget).
// ─────────────────────────────────────────────────────────────────────────

export const CHECKLIST_KEY_LABELS: Record<string, string> = {
  akb: 'АКБ', tires: 'Резина', mirrors: 'Зеркала', radio: 'Радио',
  firstaid: 'Аптечка', extinguisher: 'Огнет.', spare: 'Запаска', lkp: 'ЛКП',
}

export const FUEL_LABELS: Record<string, string> = {
  quarter: '1/4 бака', half: '1/2 бака', threequarter: '3/4 бака', full: 'Полный',
}

export const OVERALL_STATE_LABELS: Record<string, string> = {
  ok: 'Рабочее', with_remarks: 'С замечаниями', not_running: 'Не на ходу',
}

// Checklist key status → dot class
export function checkItemClass(status: string): string {
  if (status === 'ok') return 'vp-cl-ok'
  if (status === 'issue') return 'vp-cl-warn'
  return 'vp-cl-alert'
}

// Overall state → chip color
export function overallStateColor(s?: string): string {
  if (s === 'ok') return 'success'
  if (s === 'with_remarks') return 'warning'
  if (s === 'not_running') return 'error'
  return 'grey'
}

// Get status of a checklist item by key
export function clItemStatus(items: ChecklistItem[] | undefined, key: string): string {
  return items?.find(i => i.key === key)?.status ?? 'ok'
}

export function useVehicleLastChecklist() {
  const lastChecklist = ref<Checklist | null>(null)

  async function loadLastChecklist(id: number) {
    try {
      const data = await apiFetch<Checklist[]>(`/checklists/?vehicle_id=${id}`)
      const arr = Array.isArray(data) ? data : []
      if (arr.length > 0) {
        lastChecklist.value = arr.reduce((best, cur) =>
          new Date(cur.created_at) > new Date(best.created_at) ? cur : best
        )
      }
    } catch (e) {
      console.warn('[useVehicleLastChecklist] loadLastChecklist failed (silent):', e)
    }
  }

  return { lastChecklist, loadLastChecklist }
}
