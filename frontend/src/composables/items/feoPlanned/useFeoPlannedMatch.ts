// useFeoPlannedMatch — блок «похожие плановые позиции» (Шаг 4 плана
// zany-fluttering-mountain.md, POST /feo-planned-items/match): разбивка
// кандидатов на «своей категории/ветки» и «из другой категории», привязка и
// «ни одна не подходит». Вынесено дословно из FeoPlannedItemsSelect.vue
// (рефакторинг монолита, 2026-09-08).
import { computed, type Ref } from 'vue'
import type { FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import type { FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'

export interface UseFeoPlannedMatchDeps {
  props: {
    candidates?: FeoMatchCandidate[]
    readonly?: boolean
    dense?: boolean
  }
  emit: {
    (event: 'update:modelValue', val: FeoPlanSelection | null): void
    (event: 'candidate-confirmed', candidate: FeoMatchCandidate): void
  }
  denseMenuOpen: Ref<boolean>
}

export function useFeoPlannedMatch(deps: UseFeoPlannedMatchDeps) {
  const { props, emit, denseMenuOpen } = deps

  // Шаг 4 плана zany-fluttering-mountain.md — кандидаты POST /feo-planned-items/match,
  // разделённые на «своей категории/ветки» (можно привязать сразу) и «из другой
  // категории» (показываем отдельной группой как визуальную подсказку). С 2026-09-02
  // выбор кандидата из ДРУГОЙ категории (bindCandidate/selectItem — оба идут через
  // v-model в PATCH позиции закупки) обычному пользователю сервер отклонит 409-кой
  // (PLANNED_ITEM_CATEGORY_MISMATCH, распаковывается вызывающей стороной), суперадмину
  // разрешит с уведомлением — same_category тут по-прежнему только группировка в UI,
  // действие не блокируется на фронте намеренно (пусть сервер даст понятную причину).
  const sameCategoryCandidates = computed(() => (props.candidates || []).filter(c => c.same_category))
  const otherCategoryCandidates = computed(() => (props.candidates || []).filter(c => !c.same_category))

  function scoreColor(score: number): string {
    if (score >= 0.9) return 'success'
    if (score >= 0.6) return 'amber'
    return 'grey'
  }

  function bindCandidate(c: FeoMatchCandidate) {
    if (props.readonly) return
    emit('update:modelValue', { kind: c.kind, id: c.id })
    emit('candidate-confirmed', c)
  }

  function rejectSuggestions() {
    if (props.readonly) return
    // «Выбрать другую» — открыть полный список: в dense-режиме список скрыт в меню,
    // в развёрнутом он уже отображён ниже (filteredItems), просто фокус не требуется.
    if (props.dense) denseMenuOpen.value = true
  }

  return { sameCategoryCandidates, otherCategoryCandidates, scoreColor, bindCandidate, rejectSuggestions }
}
