<template>
  <!-- Шаг 4 плана zany-fluttering-mountain.md (2026-08-14): похожие по имени плановые
       позиции (POST /feo-planned-items/match) — новый блок поверх старого одиночного
       чипа suggestKey/suggestReason (тот НЕ убран — PurchaseItemsEditor.vue его тоже
       использует и не передаёт candidates, значит блок ниже там просто не рендерится,
       v-if="candidates.length"). Каждый кандидат — % совпадения + «Привязать»;
       кандидаты из чужой категории — отдельной подгруппой с пометкой (не молча). -->
  <div v-if="!readonly && candidates && candidates.length" class="feo-match-suggestions mb-2">
    <div class="feo-match-header d-flex align-center ga-1 mb-1">
      <v-icon size="18" icon="mdi-auto-fix" color="teal" />
      <span>Как мне кажется, это подходящие плановые позиции — подтвердите выбор или выберите свою ниже</span>
    </div>
    <div
      v-for="c in sameCategoryCandidates"
      :key="'cand-' + c.key"
      class="feo-match-candidate-row"
    >
      <v-chip size="small" :color="scoreColor(c.score)" variant="flat" class="feo-match-score">
        {{ Math.round(c.score * 100) }}%
      </v-chip>
      <span class="feo-match-name">{{ c.name }}</span>
      <v-btn size="small" color="primary" variant="flat" @click="$emit('bind', c)">Привязать</v-btn>
    </div>
    <div v-if="otherCategoryCandidates.length" class="mt-1">
      <div class="text-caption text-medium-emphasis">Похожие есть и в других категориях — привязка перенесёт позицию в категорию плановой позиции:</div>
      <div
        v-for="c in otherCategoryCandidates"
        :key="'cand-other-' + c.key"
        class="feo-match-candidate-row feo-match-candidate-row--other"
      >
        <v-chip size="small" :color="scoreColor(c.score)" variant="flat" class="feo-match-score">
          {{ Math.round(c.score * 100) }}%
        </v-chip>
        <span class="feo-match-name">{{ c.name }} <span class="text-caption text-medium-emphasis">— {{ c.path }}</span></span>
        <v-btn
          size="small"
          color="warning"
          variant="flat"
          :title="`Привязать и перенести позицию в категорию: ${c.path}`"
          @click="$emit('bind', c)"
        >Привязать</v-btn>
      </div>
    </div>
    <v-btn size="x-small" variant="text" class="feo-match-reject mt-1" @click="$emit('reject')">
      Больше подходящих категорий я найти не смог — попробуйте выбрать сами, может лучше получится
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
