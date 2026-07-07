import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'

export interface EntityChange {
  field_name: string
  old_value: string | null
  new_value: string | null
  changed_by_id: number | null
  changed_by_name: string | null
  changed_at: string
}

/**
 * Composable for diff-tracking (D-05..D-09, Phase 31-06).
 * Handles unseen_fields highlight + dismiss + tooltip history
 * for entity_type in {purchase, wish}. Task mechanism is separate (/tasks/{id}/dismiss-field).
 */
export function useEntityChanges(
  entityType: 'purchase' | 'wish' | 'task',
  entityId: Ref<number | null>,
  initialUnseenFields?: Ref<string[]>,
) {
  const unseenFields = ref<string[]>(initialUnseenFields?.value ?? [])
  const historyCache = ref<Record<string, EntityChange[]>>({})

  /** Sync from freshly loaded entity data */
  function syncFromEntity(fields: string[]) {
    unseenFields.value = fields ?? []
  }

  /** Reactive check — is a given field in the unseen list */
  function isFieldUnseen(f: string): boolean {
    return unseenFields.value.includes(f)
  }

  /** POST dismiss-field and remove from local unseen list */
  async function dismissField(field: string) {
    if (!entityId.value) return
    if (!isFieldUnseen(field)) return
    try {
      await apiFetch(`/entity-changes/${entityType}/${entityId.value}/dismiss-field`, {
        method: 'POST',
        body: { field_name: field } as any,
      })
      unseenFields.value = unseenFields.value.filter(f => f !== field)
    } catch (e: any) {
      // best-effort: log but don't surface to user
      console.warn('dismissField failed:', e?.payload?.message || e?.message)
    }
  }

  /**
   * GET change history for a field (cached per entity+field).
   * Returns an array of EntityChange sorted by changed_at desc.
   */
  async function getFieldHistory(field: string): Promise<EntityChange[]> {
    if (!entityId.value) return []
    const cacheKey = `${entityId.value}:${field}`
    if (historyCache.value[cacheKey]) return historyCache.value[cacheKey]
    try {
      const qs = field ? `?field=${encodeURIComponent(field)}` : ''
      const data = await apiFetch<EntityChange[]>(
        `/entity-changes/${entityType}/${entityId.value}${qs}`,
      )
      const filtered = Array.isArray(data)
        ? data.filter(c => !field || c.field_name === field)
        : []
      historyCache.value[cacheKey] = filtered
      return filtered
    } catch {
      return []
    }
  }

  return { unseenFields, isFieldUnseen, dismissField, getFieldHistory, syncFromEntity }
}
