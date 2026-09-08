// Цвета организаций на графе иерархии: палитра, чтение (БД → localStorage → палитра),
// сохранение на бэкенд с оптимистичным обновлением и откатом при конфликте (409 COLOR_TAKEN).
// Вынесено из HierarchyView.vue без изменения логики.
import { ref, type Ref } from 'vue'
import { apiFetch } from '@/api'
import type { ToastType } from '@/composables/useToast'
import type { GraphData } from './hierarchyTypes'

export const ORG_COLORS_HV = [
  '#1976d2', '#9c27b0', '#ff9800', '#009688', '#3f51b5', '#e91e63', '#795548',
  '#d32f2f', '#388e3c', '#1565c0', '#6a1b9a', '#ef6c00', '#00838f', '#c62828',
  '#2e7d32', '#283593', '#ad1457', '#4e342e', '#00695c', '#bf360c', '#0277bd',
  '#7b1fa2', '#f9a825', '#00897b', '#5c6bc0', '#d81b60', '#6d4c41', '#00acc1',
  '#e65100', '#1b5e20', '#4a148c', '#ff6f00', '#004d40', '#b71c1c', '#0d47a1',
  '#880e4f', '#33691e', '#311b92', '#e64a19', '#006064', '#827717', '#4527a0',
  '#ff8f00', '#1a237e', '#c51162', '#558b2f', '#512da8', '#ff6d00', '#0097a7',
  '#9e9d24', '#7c4dff',
]

const ORG_COLOR_KEY = 'hierarchy_org_colors'

function loadOrgColors(): Record<number, string> {
  try { return JSON.parse(localStorage.getItem(ORG_COLOR_KEY) || '{}') } catch { return {} }
}

export function useOrgColors(lastGraphData: Ref<GraphData | null>, showSnack: (text: string, color?: ToastType) => void) {
  // Phase 30.6: saveOrgColor → backend (синхронно с БД, видно везде)
  // + кэш в data.value.orgs[].color + localStorage как оптимистичный fallback
  // Phase 30.6b: проверка уникальности цвета (409 COLOR_TAKEN от бэка)
  async function saveOrgColor(orgId: number, color: string): Promise<boolean> {
    // Запомним прежнее значение для отката при конфликте
    const prev = (lastGraphData.value?.orgs.find((x: any) => x.id === orgId) as any)?.color || null
    // Optimistic update — кэш в данных графа
    if (lastGraphData.value) {
      const o = lastGraphData.value.orgs.find((x: any) => x.id === orgId) as any
      if (o) o.color = color
    }
    // localStorage — оптимистичный кэш (для других вкладок до перезагрузки графа)
    const colors = loadOrgColors()
    colors[orgId] = color
    localStorage.setItem(ORG_COLOR_KEY, JSON.stringify(colors))
    // Backend — реальное сохранение для всех клиентов / StaffView / других браузеров
    try {
      await apiFetch(`/organizations/${orgId}/color`, {
        method: 'PATCH',
        body: JSON.stringify({ color }),
      })
      return true
    } catch (e: any) {
      // Откат optimistic update
      if (lastGraphData.value) {
        const o = lastGraphData.value.orgs.find((x: any) => x.id === orgId) as any
        if (o) o.color = prev
      }
      if (prev) colors[orgId] = prev
      else delete colors[orgId]
      localStorage.setItem(ORG_COLOR_KEY, JSON.stringify(colors))

      // 409 COLOR_TAKEN — детальное сообщение с указанием орг-владельца
      const payload = e?.payload || {}
      const details = (payload.details && typeof payload.details === 'object') ? payload.details : null
      if (e?.status === 409 && (details?.code === 'COLOR_TAKEN' || payload.code === 'COLOR_TAKEN')) {
        const conflictName = details?.conflict_org_name || 'другой организации'
        showSnack(`Цвет ${color} уже назначен организации «${conflictName}». Выберите другой.`, 'warning')
        return false
      }
      console.warn('[saveOrgColor] API failed', e)
      showSnack(e?.message || 'Не удалось сохранить цвет', 'error')
      return false
    }
  }

  function getOrgColor(orgId: number, fallbackIdx: number): string {
    // Phase 30.6 source of truth: 1) backend data, 2) localStorage cache, 3) named palette
    const dbColor = (lastGraphData.value?.orgs.find((o: any) => o.id === orgId) as any)?.color
    if (dbColor) return dbColor
    const saved = loadOrgColors()[orgId]
    return saved || ORG_COLORS_HV[fallbackIdx % ORG_COLORS_HV.length]
  }

  // Color picker state
  const colorPickerOrgId = ref<number | null>(null)
  const colorPickerVisible = ref(false)
  function pickOrgColor(orgId: number) {
    colorPickerOrgId.value = orgId
    colorPickerVisible.value = true
  }

  // rebuild — колбэк перерисовки графа передаётся вызывающей стороной (View),
  // чтобы не тянуть зависимость на весь composable графа отсюда.
  async function applyOrgColor(color: string, rebuild: () => void) {
    if (colorPickerOrgId.value != null) {
      const id = colorPickerOrgId.value
      colorPickerVisible.value = false
      colorPickerOrgId.value = null
      rebuild() // instant optimistic rebuild
      const ok = await saveOrgColor(id, color) // sync to DB in background
      if (!ok) rebuild() // откат — перерисовать с прежним цветом
    }
  }

  return {
    ORG_COLORS_HV,
    getOrgColor,
    saveOrgColor,
    colorPickerOrgId,
    colorPickerVisible,
    pickOrgColor,
    applyOrgColor,
  }
}
