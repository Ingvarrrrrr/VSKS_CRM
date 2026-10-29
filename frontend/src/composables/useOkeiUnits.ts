// Единицы измерения позиции закупки — ПРАВИЛО №6: единственный источник —
// backend/app/services/units_okei.py, фронт больше не держит свою копию
// списка (frontend/src/constants/okeiUnits.ts удалён). Загружается один раз
// с GET /api/dictionaries/okei-units и кэшируется на уровне модуля — все
// компоненты (ItemsTableFlat/Stages/Wish, ItemsCardsView, PurchaseItemsEditor)
// используют этот общий кэш, повторных запросов не шлют.
//
// Приведение старых написаний («шт.» → «Штука») делает ТОЛЬКО бэкенд при
// сохранении позиции (units_okei.normalize_unit) — здесь нет второго
// приведения, только проверка «это точное название из списка?».
import { ref } from 'vue'
import { apiFetch } from '@/api'

export interface OkeiUnit { code: string; name: string }

const names = ref<string[]>([])
let loaded = false
let loadingPromise: Promise<void> | null = null

async function loadOkeiUnits(): Promise<void> {
  if (loaded) return
  if (!loadingPromise) {
    loadingPromise = apiFetch<OkeiUnit[]>('/dictionaries/okei-units')
      .then((data) => { names.value = data.map((u) => u.name); loaded = true })
      .catch(() => { /* список недоступен — isOkeiUnit временно пропустит проверку, см. ниже */ })
  }
  return loadingPromise
}

// Пустое значение — не подсвечиваем (владелец: «пустые… не трогать»). Пока
// список не загрузился — тоже не подсвечиваем (не блокируем ввод на время
// запроса/при сбое сети).
function isOkeiUnit(unit?: string | null): boolean {
  const v = (unit || '').trim()
  if (!v) return true
  if (!loaded) return true
  return names.value.includes(v)
}

function unitSelectOptions(current?: string | null): string[] {
  const v = (current || '').trim()
  if (!v || names.value.includes(v)) return names.value
  return [v, ...names.value]
}

export function useOkeiUnits() {
  void loadOkeiUnits()
  return { okeiUnitNames: names, isOkeiUnit, unitSelectOptions, loadOkeiUnits }
}
