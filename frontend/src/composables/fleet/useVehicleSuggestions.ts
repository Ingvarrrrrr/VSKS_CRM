import { ref, computed } from 'vue'
import { apiFetch } from '@/api'
import type { VehicleForm } from './vehicleDetailTypes'

// ─────────────────────────────────────────────────────────────────────────
// Автодополнение для инлайн-редактируемых полей карточки ТС (марка, модель,
// цвет, эксплуатант-текст, основание) — подсказки из уже введённых по всем
// ТС значений (/vehicles/distinct/*).
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleSuggestions(form: VehicleForm) {
  const brandSuggestions = ref<string[]>([])
  const modelSuggestions = ref<string[]>([])
  const colorSuggestions = ref<string[]>([])
  const assignedTextSuggestions = ref<string[]>([])
  const basisSuggestions = ref<string[]>([])

  async function loadSuggestions() {
    try {
      const [brands, models, colors, assignedTexts, bases] = await Promise.all([
        apiFetch<string[]>('/vehicles/distinct/brand'),
        apiFetch<string[]>('/vehicles/distinct/model'),
        apiFetch<string[]>('/vehicles/distinct/color'),
        apiFetch<string[]>('/vehicles/distinct/assigned_text'),
        apiFetch<string[]>('/vehicles/distinct/assignment_basis'),
      ])
      brandSuggestions.value = Array.isArray(brands) ? brands : []
      modelSuggestions.value = Array.isArray(models) ? models : []
      const defaultColors = ['Белый', 'Чёрный', 'Серый', 'Серебристый', 'Синий', 'Красный', 'Зелёный', 'Жёлтый', 'Коричневый', 'Бежевый']
      colorSuggestions.value = Array.from(new Set([...defaultColors, ...(Array.isArray(colors) ? colors : [])]))
      assignedTextSuggestions.value = Array.isArray(assignedTexts) ? assignedTexts : []
      const defaultBases = [
        'Договор аренды',
        'Акт приёма-передачи',
        'Договор пожертвования',
        'Договор безвозмездного пользования',
        'Закупка',
        'Передача из другой организации',
      ]
      basisSuggestions.value = Array.from(new Set([...defaultBases, ...(Array.isArray(bases) ? bases : [])]))
    } catch (e) {
      console.warn('[useVehicleSuggestions] loadSuggestions failed (silent):', e)
    }
  }

  // Модели фильтруются по выбранной марке если марка задана
  const filteredModelSuggestions = computed(() => {
    if (!form.brand || modelSuggestions.value.length === 0) return modelSuggestions.value
    // Простая фильтрация: показываем все (модели не привязаны к марке в distinct)
    return modelSuggestions.value
  })

  return {
    brandSuggestions,
    modelSuggestions,
    filteredModelSuggestions,
    colorSuggestions,
    assignedTextSuggestions,
    basisSuggestions,
    loadSuggestions,
  }
}
