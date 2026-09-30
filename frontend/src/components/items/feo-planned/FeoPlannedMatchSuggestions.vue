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
      <v-chip size="small" :color="c.occupied ? 'warning' : scoreColor(c.score)" variant="flat" class="feo-match-score">
        {{ Math.round(c.score * 100) }}%
      </v-chip>
      <span class="feo-match-name">{{ c.name }}</span>
      <!-- Владелец (30.09.2026, «Доставка из чека должна быть создана отдельно,
           она не должна объединяться ни с чем») — occupied=true (checkPlanOccupancy,
           тот же расчёт, что и в useFeoPlannedBulkMatch.ts) не блокирует ручную
           кнопку (человек может осознанно решить иначе), но подпись честно
           предупреждает, а не молчит как при чистом совпадении. -->
      <span v-if="c.occupied" class="text-caption text-warning feo-match-occupied-label">занято</span>
      <v-btn size="small" :color="c.occupied ? 'warning' : 'primary'" variant="flat" @click="$emit('bind', c)">Привязать</v-btn>
      <FeoPlanResidualSummary
        v-if="itemsByKey.get(c.key) && summaryFor(c)"
        class="feo-match-summary"
        :row="itemsByKey.get(c.key)!"
        :planned-label="summaryFor(c)!.plannedLabel"
        :consumed-label="summaryFor(c)!.consumedLabel"
        :residual-display="summaryFor(c)!.residualDisplay"
        :shortfall-label="summaryFor(c)!.shortfallLabel"
      />
      <FeoPlannedTakenBy
        v-if="itemsByKey.get(c.key)?.linked_purchases?.length || itemsByKey.get(c.key)?.linked_wishes?.length"
        class="feo-match-taken-by"
        :linked-purchases="itemsByKey.get(c.key)?.linked_purchases"
        :linked-wishes="itemsByKey.get(c.key)?.linked_wishes"
        :shortfall="shortfallFor(c)"
      />
      <div v-else-if="c.occupied" class="feo-match-taken-by text-caption text-warning">Остатка не хватает на эту позицию</div>
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
        <span v-if="c.occupied" class="text-caption text-warning feo-match-occupied-label">занято</span>
        <v-btn
          size="small"
          color="warning"
          variant="flat"
          :title="`Привязать и перенести позицию в категорию: ${c.path}`"
          @click="$emit('bind', c)"
        >Привязать</v-btn>
        <FeoPlanResidualSummary
          v-if="itemsByKey.get(c.key) && summaryFor(c)"
          class="feo-match-summary"
          :row="itemsByKey.get(c.key)!"
          :planned-label="summaryFor(c)!.plannedLabel"
          :consumed-label="summaryFor(c)!.consumedLabel"
          :residual-display="summaryFor(c)!.residualDisplay"
          :shortfall-label="summaryFor(c)!.shortfallLabel"
        />
        <FeoPlannedTakenBy
          v-if="itemsByKey.get(c.key)?.linked_purchases?.length"
          class="feo-match-taken-by"
          :linked-purchases="itemsByKey.get(c.key)?.linked_purchases"
          :shortfall="shortfallFor(c)"
        />
        <div v-else-if="c.occupied" class="feo-match-taken-by text-caption text-warning">Остатка не хватает на эту позицию</div>
      </div>
    </div>
    <!-- Жалоба владельца (сессия 29.09): когда показаны подсказки, кнопка «Создать
         новую плановую позицию» пропадала из виду — оставался только выбор из
         предложенных, даже если ни один кандидат не подходит (например, уже занят
         целиком другой закупкой). Кнопка — тот же путь, что и «Создать в плане
         закупок» внизу дерева (openCreateEntry в FeoPlannedItemsSelect.vue,
         ПРАВИЛО №6 — второй диалог создания не заводим), просто продублирована
         рядом с подсказками, чтобы её было видно сразу. -->
    <v-btn
      v-if="!readonly"
      size="x-small"
      variant="text"
      color="primary"
      prepend-icon="mdi-plus"
      class="mt-1"
      @click="$emit('create-entry')"
    >
      Создать новую плановую позицию
    </v-btn>
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
import FeoPlanResidualSummary from './FeoPlanResidualSummary.vue'
import { feoPlanRowSummary } from '@/composables/items/feoPlanned/feoPlanRowSummary'

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
  /** Жалоба владельца (29.09): «Создать новую плановую позицию» рядом с
   *  подсказками — родитель (FeoPlannedItemsSelect.vue) открывает ТОТ ЖЕ диалог,
   *  что и кнопка «Создать в плане закупок» (openCreateEntry). */
  'create-entry': []
}>()

const itemsByKey = computed(() => {
  const map = new Map<string, FeoPlanPosition>()
  for (const r of props.items || []) map.set(r.key, r)
  return map
})

/** Разница «сумма новой позиции минус остаток кандидата» (сумма-residual):
 *  > 0 — не хватает (FeoPlannedTakenBy покажет красное «не хватает N»); <= 0 —
 *  остатка достаточно (спокойное «остаток хватает»); null — сумма новой позиции
 *  ЕЩЁ неизвестна, достаточность не проверить (тогда FeoPlannedTakenBy покажет
 *  прежнее нейтрально-тревожное «если это дубль» — владелец, 30.09.2026:
 *  «в остатка хватает — не пугать неуместным предупреждением»). ВАЖНО: раньше
 *  и «хватает», и «неизвестно» схлопывались в один null — из-за этого «дубль,
 *  разберитесь» показывался даже при достаточном остатке (тот самый баг).
 *  Единственное место этого расчёта (Правило №6) — та же row.residual, что и
 *  FeoPlanResidualSummary.vue ниже. */
function shortfallFor(c: FeoMatchCandidate): number | null {
  if (props.amount == null) return null
  const row = itemsByKey.value.get(c.key)
  if (!row) return null
  return props.amount - (row.residual ?? 0)
}

// «План · выбрано · остаток · не хватает» сводка кандидата (владелец,
// 30.09.2026: «в подходящих не видно, сколько запланировано и сколько
// выбрано») — тот же feoPlanRowSummary.ts, что и FeoPlannedItemRow.vue
// (useFeoPlannedRows.ts::rowDisplayProps), второй расчёт не заводим. Здесь нет
// контекста «уже занято в этой форме» (pendingByPlannedItem) — consumed/residual
// берутся прямо с сервера (row.consumed/row.residual), shortfall — тот же
// shortfallFor выше, но в знаке feoPlanRowSummary (остаток минус сумма,
// отрицательный = не хватает) — обратный знак к shortfallFor, поэтому минус.
function summaryFor(c: FeoMatchCandidate) {
  const row = itemsByKey.value.get(c.key)
  if (!row) return null
  const gap = shortfallFor(c)
  return feoPlanRowSummary(row, row.consumed, row.residual, gap != null ? -gap : null)
}
</script>
