// Переключатель «целиком / товары-услуги» для KPI-карточек дашборда и карточки
// субсидии + активный фильтр расшифровки по типу (клик по строке «товары»/
// «услуги»/«без типа») — план ancient-prancing-music.md, раздел C (21.09.2026).
// Module-level singleton (по образцу composables/subsidies/useFeoTreePrefs.ts/
// useKpiDrilldown.ts) — ОБЩИЙ для дашборда и карточки субсидии (владелец: «тот
// же переключатель»): KpiCardsWidget.vue и SubsidyKpiCards.vue читают/пишут
// ЭТИ ЖЕ refs, а не заводят по копии на каждый экран (Правило №6).
import { ref, watch } from 'vue'
import type { ItemTypeKind } from '@/utils/itemTypeKind'

export type KpiTypeSplitMode = 'total' | 'split'

export interface KpiActiveTypeFilter {
  stage: string
  kind: ItemTypeKind
}

const KPI_TYPE_SPLIT_KEY = 'kpi_type_split_mode'

function loadKpiTypeSplit(): KpiTypeSplitMode {
  try {
    const raw = localStorage.getItem(KPI_TYPE_SPLIT_KEY)
    if (raw === 'split' || raw === 'total') return raw
  } catch {
    // localStorage недоступен (приватный режим и т.п.) — не критично
  }
  return 'total'
}

let _api: ReturnType<typeof buildKpiPrefs> | null = null

export function useKpiPrefs() {
  if (!_api) _api = buildKpiPrefs()
  return _api
}

function buildKpiPrefs() {
  const kpiTypeSplit = ref<KpiTypeSplitMode>(loadKpiTypeSplit())
  // Активная строка-фильтр («этот этап, этот тип») — открывает
  // StageFeoDrillDialog и подсвечивает строку карточки; НЕ персистится
  // (сбрасывается при закрытии диалога/перезагрузке, как и остальные
  // drill-down фильтры проекта, см. useKpiDrilldown.ts).
  const activeTypeFilter = ref<KpiActiveTypeFilter | null>(null)

  watch(kpiTypeSplit, (v) => {
    try {
      localStorage.setItem(KPI_TYPE_SPLIT_KEY, v)
    } catch {
      // не критично
    }
  })

  // Клик по той же строке — снять фильтр (владелец: «повторный клик — выключает»).
  function toggleTypeFilter(stage: string, kind: ItemTypeKind): boolean {
    const cur = activeTypeFilter.value
    if (cur && cur.stage === stage && cur.kind === kind) {
      activeTypeFilter.value = null
      return false
    }
    activeTypeFilter.value = { stage, kind }
    return true
  }

  function clearTypeFilter() {
    activeTypeFilter.value = null
  }

  return { kpiTypeSplit, activeTypeFilter, toggleTypeFilter, clearTypeFilter }
}
