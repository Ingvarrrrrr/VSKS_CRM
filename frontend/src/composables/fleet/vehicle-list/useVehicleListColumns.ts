// useVehicleListColumns.ts — конфигурация колонок реестра ТС (useColumnConfig)
// + сортировка по клику в ColumnHeaderMenu. Дословный перенос из
// VehicleListView.vue.
import { ref, computed } from 'vue'
import { useColumnConfig, type ColumnDef } from '@/composables/useColumnConfig'

export const allColumns: ColumnDef[] = [
  { key: 'plate',              title: 'Гос. №',         width: 170, group: 'core' },
  { key: 'brand_model',        title: 'Марка/Модель',    width: 200, group: 'core' },
  { key: 'vin',                title: 'VIN',             width: 160, group: 'all'  },
  { key: 'type_label',         title: 'Тип',             width: 140, group: 'core' },
  { key: 'state_label',        title: 'Состояние',       width: 130, group: 'core' },
  { key: 'owner_org_name',     title: 'Владелец',        width: 180, group: 'core' },
  { key: 'assigned_label',     title: 'Эксплуатант',     width: 180, group: 'core' },
  { key: 'insurance_until',    title: 'ОСАГО до',        width: 120, group: 'core' },
  { key: 'current_odometer_km',title: 'Пробег км',       width: 110, group: 'core' },
  { key: 'next_to_km',         title: 'След. ТО км',     width: 110, group: 'all'  },
  { key: 'fuel_type',          title: 'Топливо',         width: 100, group: 'all'  },
  { key: 'actions',            title: '',                width: 40,  group: 'core' },
]

export function useVehicleListColumns() {
  // Используем статичный tableId чтобы избежать race condition: если userId undefined
  // на mount (auth/me ещё не вернулся), LS-ключ становится "vehicles_list_uundefined"
  // и при следующей загрузке создаётся новый пустой ключ → fallback на allColumns.
  // Per-user изоляция не нужна — localStorage уже per-browser.
  const cfg = useColumnConfig('vehicles_list', allColumns)

  // Workaround Vuetify v-data-table dev-mode bug: `:headers="cfg.visibleHeaders"`
  // иногда падает с `_headers.slice is not a function` потому что Vuetify watcher
  // получает Vue reactive Proxy на массив, и `.slice()` теряется через прокси.
  // Plain-array copy через Array.from стабилизирует — prod-build не падает,
  // dev (Vite + Vuetify HMR) — да.
  const dtHeaders = computed(() => Array.from(cfg.visibleHeaders.value ?? []))

  const showColumnPicker = ref(false)

  const sortBy = ref<string | null>(null)
  const sortDesc = ref(false)

  function getSortBy(key: string): 'asc' | 'desc' | null {
    if (sortBy.value !== key) return null
    return sortDesc.value ? 'desc' : 'asc'
  }

  function applySort(key: string, dir: 'asc' | 'desc' | null) {
    if (dir === null) { sortBy.value = null; sortDesc.value = false }
    else { sortBy.value = key; sortDesc.value = dir === 'desc' }
  }

  return {
    cfg,
    allColumns,
    dtHeaders,
    showColumnPicker,
    sortBy,
    sortDesc,
    getSortBy,
    applySort,
  }
}
