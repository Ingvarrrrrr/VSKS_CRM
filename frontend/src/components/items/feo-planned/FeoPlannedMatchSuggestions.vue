<template>
  <!-- Шаг 4 плана zany-fluttering-mountain.md (2026-08-14): похожие по имени плановые
       позиции (POST /feo-planned-items/match) — новый блок поверх старого одиночного
       чипа suggestKey/suggestReason (тот НЕ убран — PurchaseItemsEditor.vue его тоже
       использует и не передаёт candidates, значит блок ниже там просто не рендерится,
       v-if="candidates.length"). Каждый кандидат — % совпадения + «Привязать»;
       кандидаты из чужой категории — отдельной подгруппой с пометкой (не молча). -->
  <div v-if="!readonly && candidates && candidates.length" class="feo-match-suggestions mb-2">
    <div class="text-caption text-medium-emphasis d-flex align-center ga-1 mb-1">
      <v-icon size="14" icon="mdi-auto-fix" />
      <span>Похожие плановые позиции — подтвердите выбор или выберите свою ниже</span>
    </div>
    <div
      v-for="c in sameCategoryCandidates"
      :key="'cand-' + c.key"
      class="feo-match-candidate-row"
    >
      <v-chip size="small" :color="scoreColor(c.score)" variant="tonal" class="feo-match-score">
        {{ Math.round(c.score * 100) }}%
      </v-chip>
      <span class="feo-match-name">{{ c.name }}</span>
      <v-btn size="x-small" color="primary" variant="tonal" @click="$emit('bind', c)">Привязать</v-btn>
    </div>
    <div v-if="otherCategoryCandidates.length" class="mt-1">
      <div class="text-caption text-medium-emphasis">Похожие есть и в других категориях — привязка перенесёт позицию в категорию плановой позиции:</div>
      <div
        v-for="c in otherCategoryCandidates"
        :key="'cand-other-' + c.key"
        class="feo-match-candidate-row feo-match-candidate-row--other"
      >
        <v-chip size="small" color="grey" variant="tonal" class="feo-match-score">
          {{ Math.round(c.score * 100) }}%
        </v-chip>
        <span class="feo-match-name">{{ c.name }} <span class="text-caption text-medium-emphasis">— {{ c.path }}</span></span>
        <v-btn
          size="x-small"
          color="warning"
          variant="tonal"
          :title="`Привязать и перенести позицию в категорию: ${c.path}`"
          @click="$emit('bind', c)"
        >Привязать</v-btn>
      </div>
    </div>
    <v-btn size="x-small" variant="text" color="primary" class="mt-1" @click="$emit('reject')">
      Ни одна не подходит — выбрать вручную
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import type { FeoMatchCandidate } from '@/composables/useFeoPlanMatching'

defineProps<{
  candidates?: FeoMatchCandidate[]
  readonly?: boolean
  sameCategoryCandidates: FeoMatchCandidate[]
  otherCategoryCandidates: FeoMatchCandidate[]
  scoreColor: (score: number) => string
}>()

defineEmits<{
  bind: [candidate: FeoMatchCandidate]
  reject: []
}>()
</script>
