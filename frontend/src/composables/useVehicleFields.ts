import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'

// ─────────────────────────────────────────────────────────────────────────
// Реестр полей карточки ТС — синглтон по образцу useOrgConfig.ts.
// Источник правды: backend/app/services/vehicle_fields.py (см. §2, §4 контракта
// AUTOBLOCK_FIELDS_SPEC.md). Данные грузятся один раз за сессию (module-level
// state), сбрасываются только явным loadFields(true) после сохранения.
// ─────────────────────────────────────────────────────────────────────────

export type VehicleFieldType = 'string' | 'text' | 'int' | 'float' | 'date' | 'bool' | 'enum' | 'org' | 'readonly'
export type VehicleFieldStorage = 'column' | 'props' | 'computed'

export interface VehicleFieldDescriptor {
  key: string
  label: string
  type: VehicleFieldType
  storage: VehicleFieldStorage
  hidden: boolean
  /** false = обязательное поле, скрыть нельзя (несмотря на название — так задано в контракте) */
  lockable: boolean
  required: boolean
  /**
   * Допустимые значения поля — из правил проверки данных листа владельца
   * (backend/app/services/vehicle_sheet_dictionaries.py). Присутствует ТОЛЬКО
   * у полей с жёстким справочником (авторезина, состояние резины/ЛКП, кузов,
   * пропуска, техосмотр и т.п.) — единственный источник для выпадающих
   * списков карточки ТС, второй копии на фронте не держим.
   */
  options?: string[]
  /**
   * Пояснение "откуда берётся значение" для полей, которые не заполняются
   * напрямую пользователем (backend/app/services/vehicle_fields.py, §4).
   * Присутствует только у части полей — остальные заполняются вручную и
   * пояснения не требуют.
   */
  source_hint?: string
}

export interface VehicleFieldGroup {
  key: string
  title: string
  fields: VehicleFieldDescriptor[]
}

/**
 * Блок карточки ТС, НЕ входящий в реестр полей (отдельная вкладка/сущность —
 * история передач, штрафы, путевые листы и т.п.), с пояснением источника
 * данных. См. backend/app/services/vehicle_fields.get_related_blocks().
 */
export interface VehicleRelatedBlock {
  key: string
  title: string
  source_hint: string
}

export interface VehicleFieldsResponse {
  can_manage: boolean
  groups: VehicleFieldGroup[]
  hidden_keys: string[]
  related_blocks: VehicleRelatedBlock[]
}

export interface VehicleFieldUpdateItem {
  field_key: string
  is_hidden: boolean
}

function extractErrorMessage(err: any): string {
  const status = err?.status ? ` (HTTP ${err.status})` : ''
  const msg = err?.payload?.message || err?.detail || err?.message || 'Неизвестная ошибка'
  return `${msg}${status}`
}

// Module-level singleton state — общий на всё приложение
const groups = ref<VehicleFieldGroup[]>([])
const hiddenKeys = ref<Set<string>>(new Set())
const canManage = ref(false)
const loaded = ref(false)
const loading = ref(false)
const relatedBlocks = ref<VehicleRelatedBlock[]>([])

export function useVehicleFields() {
  async function loadFields(force = false) {
    if ((loaded.value || loading.value) && !force) return
    loading.value = true
    try {
      const data = await apiFetch<VehicleFieldsResponse>('/vehicle-fields')
      groups.value = Array.isArray(data?.groups) ? data.groups : []
      hiddenKeys.value = new Set(Array.isArray(data?.hidden_keys) ? data.hidden_keys : [])
      canManage.value = !!data?.can_manage
      relatedBlocks.value = Array.isArray(data?.related_blocks) ? data.related_blocks : []
      loaded.value = true
    } catch (err: any) {
      // Fail-open: не загрузили реестр — ничего не скрываем, показываем все поля,
      // но сообщаем пользователю об ошибке (не глотаем молча).
      const toast = useToast()
      toast.error(`Не удалось загрузить состав полей карточки ТС: ${extractErrorMessage(err)}`)
      groups.value = []
      hiddenKeys.value = new Set()
      canManage.value = false
      relatedBlocks.value = []
    } finally {
      loading.value = false
    }
  }

  /** Видимо ли поле для текущей организации. Пока реестр не загружен (или упал) — считаем видимым. */
  function isFieldVisible(key: string): boolean {
    if (!loaded.value) return true
    return !hiddenKeys.value.has(key)
  }

  /** Скрыта ли целиком группа (все её поля скрыты) — чтобы не рисовать пустой заголовок секции. */
  function isGroupVisible(groupKey: string): boolean {
    const group = groups.value.find(g => g.key === groupKey)
    if (!group || group.fields.length === 0) return true
    return group.fields.some(f => !hiddenKeys.value.has(f.key))
  }

  /** Допустимые значения поля из реестра (см. VehicleFieldDescriptor.options), либо
   * undefined, если у поля нет жёсткого справочника (или реестр ещё не загружен). */
  function getFieldOptions(key: string): string[] | undefined {
    for (const group of groups.value) {
      const field = group.fields.find(f => f.key === key)
      if (field) return field.options
    }
    return undefined
  }

  /** Подпись поля из реестра (единственный источник правды —
   * backend/app/services/vehicle_fields.py). undefined, если поле не найдено
   * в реестре (не загружен ещё / неизвестный ключ) — вызывающая сторона
   * должна в этом случае использовать собственный запасной текст, а не
   * держать вторую копию подписей на фронте. */
  function getFieldLabel(key: string): string | undefined {
    for (const group of groups.value) {
      const field = group.fields.find(f => f.key === key)
      if (field) return field.label
    }
    return undefined
  }

  /** Пояснение "откуда берётся значение" для поля (VehicleFieldDescriptor.source_hint),
   * либо undefined — у большинства полей его нет (заполняются вручную) или реестр
   * ещё не загружен. */
  function getFieldSourceHint(key: string): string | undefined {
    for (const group of groups.value) {
      const field = group.fields.find(f => f.key === key)
      if (field) return field.source_hint
    }
    return undefined
  }

  /** Пояснение источника данных для НЕ-полевого блока карточки (вкладки История,
   * Штрафы, Путевые листы и т.п.) — см. VehicleRelatedBlock. */
  function getRelatedBlockHint(key: string): string | undefined {
    return relatedBlocks.value.find(b => b.key === key)?.source_hint
  }

  async function saveFields(items: VehicleFieldUpdateItem[]) {
    try {
      await apiFetch('/vehicle-fields', {
        method: 'PUT',
        body: JSON.stringify({ items }),
      })
      await loadFields(true)
    } catch (err: any) {
      const toast = useToast()
      toast.error(extractErrorMessage(err))
      throw err
    }
  }

  return {
    groups,
    hiddenKeys,
    canManage,
    loading,
    loaded,
    relatedBlocks,
    loadFields,
    isFieldVisible,
    isGroupVisible,
    getFieldOptions,
    getFieldLabel,
    getFieldSourceHint,
    getRelatedBlockHint,
    saveFields,
  }
}
