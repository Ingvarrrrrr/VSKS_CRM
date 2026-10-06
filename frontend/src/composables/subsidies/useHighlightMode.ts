// Единственный источник «какая подсветка дерева ФЭО сейчас активна» — KPI-
// плитки (useKpiDrilldown.ts) или «где превышение» (useExcessDrilldown.ts,
// задание владельца 06.10.2026). Оба режима красят строки дерева по-своему —
// активировать их ОДНОВРЕМЕННО нельзя, иначе непонятно, что показывает
// подсветка. Вместо того чтобы одному composable звать API другого напрямую
// (циклический импорт между useKpiDrilldown.ts и useExcessDrilldown.ts), оба
// читают/пишут этот один ref и сами гасят себя, когда активным стал другой
// режим (Правило №6 — один переключатель, не пара взаимных вызовов).
import { ref } from 'vue'

export type HighlightMode = 'kpi' | 'excess' | null

export const activeHighlightMode = ref<HighlightMode>(null)
