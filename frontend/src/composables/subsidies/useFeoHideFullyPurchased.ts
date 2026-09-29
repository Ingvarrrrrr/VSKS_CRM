// Переключатель «Скрыть закупленные полностью» (владелец, 30.09.2026) — один
// флажок на всё дерево ФЭО + панель Ур.5, не per-node состояние. Module-level
// singleton (тот же приём, что и useFeoUndoStack.ts/useFeoLevel5.ts, см.
// докстринг usePlanToRequest.ts про Правило №6) — FeoTreeToolbar.vue (сам
// переключатель), FeoTreeRow.vue (скрыть строку категории) и
// FeoLevel5Panel.vue (скрыть строку плановой позиции) читают ОДНО и то же
// значение, второй Set/ref не заводим.
//
// localStorage — только косметическое запоминание выбора между сессиями, по
// умолчанию выключен (владелец: «По умолчанию выключен»). Чтение/запись в
// try/catch (память feedback: приватный режим браузера/заблокированное
// хранилище не должны ронять страницу).
import { ref, watch } from 'vue'

const STORAGE_KEY = 'feo_hide_fully_purchased'

function readInitial(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

const hideFullyPurchased = ref<boolean>(readInitial())

watch(hideFullyPurchased, (v) => {
  try {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
  } catch {
    // приватный режим/заблокировано — просто не запоминаем между сессиями
  }
})

export function useFeoHideFullyPurchased() {
  return { hideFullyPurchased }
}
