// Статус «нужности» плановой позиции ФЭО (FeoPlannedItem.need_level), владелец
// 04.10.2026 — зеркалит backend/app/services/plan_need_level.py (ПРАВИЛО №6,
// единственный источник констант/подписей на фронте). Второй список значений
// или свой текст подписи по компонентам не заводить — PlannedItemAddDialog.vue/
// PlannedItemEditDialog.vue (форма), FeoLevel5Panel.vue (чип в дереве) и
// PlanToOrderDialog.vue (группировка «что ещё заказать») читают только отсюда.
export type NeedLevel = 'likely' | 'nice_to_have'

export const NEED_LEVEL_LIKELY: NeedLevel = 'likely'
export const NEED_LEVEL_NICE_TO_HAVE: NeedLevel = 'nice_to_have'

export const NEED_LEVELS: NeedLevel[] = [NEED_LEVEL_LIKELY, NEED_LEVEL_NICE_TO_HAVE]

export const NEED_LEVEL_LABELS: Record<NeedLevel, string> = {
  likely: 'Скорее всего понадобится',
  nice_to_have: 'Хотелось бы, но можно и отказаться',
}

// Короткая подпись для узкого чипа в дереве ФЭО (FeoLevel5Panel.vue) — полная
// подпись уходит в title/tooltip, см. NEED_LEVEL_LABELS.
export const NEED_LEVEL_SHORT_LABELS: Record<NeedLevel, string> = {
  likely: 'нужно',
  nice_to_have: 'хотелось бы',
}

export const NEED_LEVEL_OPTIONS: { value: NeedLevel; title: string }[] = [
  { value: NEED_LEVEL_LIKELY, title: NEED_LEVEL_LABELS.likely },
  { value: NEED_LEVEL_NICE_TO_HAVE, title: NEED_LEVEL_LABELS.nice_to_have },
]

// Безхозные строки (план без отдельной FeoPlannedItem — kind='plan_position'/
// 'feo_article', у category-плана нет own need_level; либо значение не пришло
// вовсе) трактуются как 'likely' — то же правило, что и на бэкенде (см.
// normalize_need_level/docstring compute_feo_plan_tree, Задача 2 владельца
// 04.10.2026): «молчание» не трактуется как необязательность плана.
export function needLevelOf(value?: string | null): NeedLevel {
  return value === NEED_LEVEL_NICE_TO_HAVE ? NEED_LEVEL_NICE_TO_HAVE : NEED_LEVEL_LIKELY
}
