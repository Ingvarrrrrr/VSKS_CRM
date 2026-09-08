import { ref, computed } from 'vue'
import { searchCities, cityDisplayLabel } from '@/components/fleet/russiaCitiesCatalog'

// ─────────────────────────────────────────────────────────────────────────
// Автодополнение городов для полей «Место нахождения» и «Место постоянной
// приписки ТС» — по общему справочнику населённых пунктов России
// (components/fleet/russiaCitiesCatalog.ts, не дублируется). Каждое поле
// держит свой независимый ref строки поиска, иначе ввод в одном
// автодополнении сбрасывал бы список подсказок другого.
// ─────────────────────────────────────────────────────────────────────────

export function useVehicleCityAutocomplete() {
  // 2026-09 (geo-fix #4): автодополнение «Место нахождения, город» по
  // справочнику населённых пунктов России. Свободный ввод не запрещён
  // (v-combobox, не v-select) — в базе уже есть значения вроде "ДНР г.
  // Донецк", ломать их нельзя. Список подсказок считается от текста,
  // который печатает пользователь, а не от полного каталога (~3 тыс.
  // записей) — no-filter на v-combobox отключает встроенную фильтрацию
  // Vuetify, чтобы не фильтровать уже отфильтрованный (и уже ограниченный
  // по количеству) список повторно.
  const locationCitySearch = ref('')
  const locationCityItems = computed(() =>
    searchCities(locationCitySearch.value || '', 30).map(cityDisplayLabel)
  )

  // Отдельное поле-справочник «Место постоянной приписки ТС» (home_base_city,
  // доделка 2026-09) — тот же каталог/поиск, но независимый ref для
  // search-текста.
  const homeBaseCitySearch = ref('')
  const homeBaseCityItems = computed(() =>
    searchCities(homeBaseCitySearch.value || '', 30).map(cityDisplayLabel)
  )

  return {
    locationCitySearch,
    locationCityItems,
    homeBaseCitySearch,
    homeBaseCityItems,
  }
}
