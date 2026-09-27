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
      <FeoPlannedTakenBy
        v-if="itemsByKey.get(c.key)?.linked_purchases?.length"
        class="feo-match-taken-by"
        :linked-purchases="itemsByKey.get(c.key)?.linked_purchases"
        :shortfall="shortfallFor(c)"
      />
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
        <FeoPlannedTakenBy
          v-if="itemsByKey.get(c.key)?.linked_purchases?.length"
          class="feo-match-taken-by"
          :linked-purchases="itemsByKey.get(c.key)?.linked_purchases"
          :shortfall="shortfallFor(c)"
        />
      </div>
    </div>
    <v-btn size="x-small" variant="text" class="feo-match-reject mt-1" @click="$emit('reject')">
      Больше подходящих категорий я найти не смог — попробуйте выбрать сами, может лучше получится
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import FeoPlannedTakenBy from './FeoPlannedTakenBy.vue'

const props = defineProps<{
  candidates?: FeoMatchCandidate[]
  readonly?: boolean
  sameCategoryCandidates: FeoMatchCandidate[]
  otherCategoryCandidates: FeoMatchCandidate[]
  scoreColor: (score: number) => string
  /** Уже загруженные плановые позиции (FeoPlannedItemsSelect.vue props.items) —
   *  лукап по composite key, тот же приём, что и useFeoPlannedSearch.ts::itemsByKey
   *  (ПРАВИЛО №6, второй движок не заводим): нужен только чтобы прочитать
   *  linked_purchases/residual кандидата, которых нет в самом FeoMatchCandidate. */
  items?: FeoPlanPosition[]
  /** Сумма позиции, которую сейчас пытаются привязать — для предупреждения
   *  «не хватает N ₽», если план кандидата уже занят целиком/частично. */
  amount?: number | null
}>()

defineEmits<{
  bind: [candidate: FeoMatchCandidate]
  reject: []
}>()

const itemsByKey = computed(() => {
  const map = new Map<string, FeoPlanPosition>()
  for (const r of props.items || []) map.set(r.key, r)
  return map
})

/** Не хватает ли остатка кандидата на сумму текущей позиции — null, если сумма
 *  неизвестна или остатка хватает (тогда FeoPlannedTakenBy покажет оранжевое
 *  предупреждение вместо красного, см. её проп shortfall). */
function shortfallFor(c: FeoMatchCandidate): number | null {
  if (props.amount == null) return null
  const row = itemsByKey.value.get(c.key)
  if (!row) return null
  const residual = row.residual ?? 0
  const gap = props.amount - residual
  return gap > 0 ? gap : null
}
</script>
