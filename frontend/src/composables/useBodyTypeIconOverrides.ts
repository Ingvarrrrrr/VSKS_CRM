import { ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast } from '@/composables/useToast'
import { resolveBodyTypeIcon, type BodyTypeIconResult } from '@/components/vehicles/bodyTypeIcon'

// ─────────────────────────────────────────────────────────────────────────
// Переопределения значков кузова ТС по организации — синглтон по образцу
// useVehicleFields.ts. Источник правды на сервере:
// backend/app/services/body_type_icons.py + app/routers/body_type_icons.py.
// Значение по умолчанию (когда переопределения нет) остаётся хардкодом в
// bodyTypeIcon.ts — эта composable только накладывает поверх него отличия,
// загруженные с сервера.
// ─────────────────────────────────────────────────────────────────────────

export interface BodyTypeIconOverrideItem {
  icon_kind: 'img' | 'mdi'
  icon_value: string
}

export interface BodyTypeIconsResponse {
  can_manage: boolean
  overrides: Record<string, BodyTypeIconOverrideItem>
}

function extractErrorMessage(err: any): string {
  const status = err?.status ? ` (HTTP ${err.status})` : ''
  const msg = err?.payload?.message || err?.detail || err?.message || 'Неизвестная ошибка'
  return `${msg}${status}`
}

// Module-level singleton state — общий на всё приложение (как groups/hiddenKeys в useVehicleFields).
const overrides = ref<Record<string, BodyTypeIconOverrideItem>>({})
const canManage = ref(false)
const loaded = ref(false)
const loading = ref(false)

export function useBodyTypeIconOverrides() {
  /**
   * Пассивная загрузка (вызывается из VehicleTypeIcon.vue при каждом монтировании,
   * дедуплицируется флагом loaded/loading — реальный fetch уходит один раз).
   * Ошибку НЕ показываем тостом здесь: карточка/список с десятками значков не
   * должны спамить пользователя — молча остаёмся на дефолтах (fail-open).
   * Для явной перезагрузки после сохранения в редакторе — force=true, ошибку
   * в этом случае обрабатывает вызывающий редактор.
   */
  async function loadOverrides(force = false) {
    if ((loaded.value || loading.value) && !force) return
    loading.value = true
    try {
      const data = await apiFetch<BodyTypeIconsResponse>('/body-type-icons')
      overrides.value = (data && typeof data.overrides === 'object') ? data.overrides : {}
      canManage.value = !!data?.can_manage
      loaded.value = true
    } catch (err: any) {
      console.warn('[body-type-icons] не удалось загрузить переопределения значков кузова:', err)
      if (!loaded.value) {
        overrides.value = {}
        loaded.value = true // не долбим бэкенд повторно каждым отрисованным значком
      }
    } finally {
      loading.value = false
    }
  }

  /** Эффективный значок кузова: переопределение организации, иначе дефолт из bodyTypeIcon.ts. */
  function resolveIcon(bodyType?: string | null): BodyTypeIconResult | null {
    if (!bodyType) return null
    const ov = overrides.value[bodyType]
    if (ov) {
      return ov.icon_kind === 'img'
        ? { kind: 'img', file: ov.icon_value }
        : { kind: 'mdi', icon: ov.icon_value }
    }
    return resolveBodyTypeIcon(bodyType)
  }

  function isOverridden(bodyType: string): boolean {
    return Object.prototype.hasOwnProperty.call(overrides.value, bodyType)
  }

  async function saveOverride(bodyType: string, icon: BodyTypeIconOverrideItem) {
    try {
      await apiFetch(`/body-type-icons/${encodeURIComponent(bodyType)}`, {
        method: 'PUT',
        body: JSON.stringify(icon),
      })
      await loadOverrides(true)
    } catch (err: any) {
      const toast = useToast()
      toast.error(`Не удалось сохранить значок «${bodyType}»: ${extractErrorMessage(err)}`)
      throw err
    }
  }

  async function resetOverride(bodyType: string) {
    try {
      await apiFetch(`/body-type-icons/${encodeURIComponent(bodyType)}`, { method: 'DELETE' })
      await loadOverrides(true)
    } catch (err: any) {
      const toast = useToast()
      toast.error(`Не удалось сбросить значок «${bodyType}»: ${extractErrorMessage(err)}`)
      throw err
    }
  }

  async function resetAllOverrides() {
    try {
      await apiFetch('/body-type-icons', { method: 'DELETE' })
      await loadOverrides(true)
    } catch (err: any) {
      const toast = useToast()
      toast.error(`Не удалось сбросить значки к умолчанию: ${extractErrorMessage(err)}`)
      throw err
    }
  }

  return {
    overrides,
    canManage,
    loaded,
    loading,
    loadOverrides,
    resolveIcon,
    isOverridden,
    saveOverride,
    resetOverride,
    resetAllOverrides,
  }
}
