// Единственный источник обхода поддерева категорий ФЭО по parent_id — раньше
// collectSubtreeIds жила только как локальная функция в SubsidiesView.vue и уже
// использовалась в четырёх местах (feoParentOptions, feoDeleteChildrenCount,
// drag&drop категорий). Вынесена сюда параметризованной по списку категорий,
// чтобы компоненты диалогов ФЭО (FeoCategoryDialog/FeoCategoryDeleteDialog) не
// заводили свою копию (Правило №6).
import type { FeoCategory } from './types'

export function collectSubtreeIds(categories: FeoCategory[], nodeId: number): number[] {
  const ids = [nodeId]
  const find = (pid: number) => {
    for (const c of categories) {
      if (c.parent_id === pid) { ids.push(c.id); find(c.id) }
    }
  }
  find(nodeId)
  return ids
}
