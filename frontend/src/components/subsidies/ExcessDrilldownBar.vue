<template>
  <!-- Плавающая панель навигации «где превышение» (задание владельца
       06.10.2026). Рисует себя только когда useExcessDrilldown() активен —
       activate() кем-то вызван (чип в SubsidyKpiCards.vue/FeoTreeRow.vue).
       Фиксированная позиция снизу экрана — не зависит от того, где именно в
       вёрстке SubsidiesView.vue стоит дерево ФЭО, и не ломается при скролле
       длинного дерева.

       Шапка (иконка + заголовок + ✕) и строка управления (‹ N из M ›
       + «список статей») — ВСЕГДА видимы, никогда не участвуют в переносе
       вместе с длинным текстом (приёмка 06.10.2026, дефект 1: на 390×844 ‹1
       из 4› и ✕ были не видны). Текст/строка-разница/список статей — в
       .excess-bar__body со своим max-height и прокруткой, чтобы длинный
       текст/раскрытый список не выталкивал управляющую строку за экран. -->
  <div v-if="excessDrilldown.activeKind.value" class="excess-bar">
    <div class="excess-bar__header">
      <v-icon icon="mdi-crosshairs-gps" size="16" color="orange-darken-2" />
      <span class="excess-bar__title">
        {{ excessDrilldown.hasTargets.value && !excessDrilldown.isComposition.value ? excessDrilldown.kindLabel.value : 'Где превышение' }}
      </span>
      <v-btn icon size="x-small" variant="text" class="excess-bar__close" title="Закрыть" @click="excessDrilldown.clear()">
        <v-icon icon="mdi-close" size="16" />
      </v-btn>
    </div>

    <div class="excess-bar__body">
      <!-- Дефект 1 приёмки 06.10.2026 (composition-режим, главный случай
           владельца — субсидия «ФАДМ 2026_2»): узловой контроль 0 везде,
           стрелки просто показывают, из чего складывается итог — другой
           заголовок, не «N статей на сумму» (той суммы по отдельным
           статьям тут нет, см. докстринг buildCompositionMessage). -->
      <span v-if="excessDrilldown.hasTargets.value && excessDrilldown.isComposition.value" class="excess-bar__text">
        {{ excessDrilldown.compositionMessage.value }}
      </span>
      <span v-else-if="excessDrilldown.hasTargets.value" class="excess-bar__text">
        {{ excessDrilldown.kindLabel.value }}: {{ excessDrilldown.targets.value.length }}
        {{ excessDrilldown.targets.value.length === 1 ? 'статья' : 'статьи' }}
        на {{ formatCurrency(excessDrilldown.targetsTotal.value) }}
      </span>
      <span v-else class="excess-bar__text">{{ excessDrilldown.emptyMessage.value }}</span>

      <!-- Дефект 3 приёмки: сумма статей-виновников ≠ сумме в чипе субсидии —
           объясняем разницу одной строкой, только в обычном режиме (в
           composition-режиме «сумма статей» не имеет того же смысла, см.
           докстринг diffLine в useExcessDrilldown.ts). -->
      <div v-if="excessDrilldown.diffLine.value" class="excess-bar__diff">
        {{ excessDrilldown.diffLine.value }}
      </div>

      <div v-if="listOpen && excessDrilldown.hasTargets.value" class="excess-bar__list">
        <!-- Дефект 2 приёмки: ОБА числа вида (план/ФЭО или закупки/план) по
             каждой статье + превышение, если оно на ней есть (ноль в
             composition-режиме — честно, виновника по отдельности там нет). -->
        <div
          v-for="(row, idx) in excessDrilldown.targetRows()"
          :key="row.id"
          class="excess-bar__list-item"
          :class="{ 'excess-bar__list-item--current': idx === excessDrilldown.currentIndex.value }"
          @click="excessDrilldown.goTo(idx)"
        >
          <span class="excess-bar__list-name">{{ row.name }}</span>
          <!-- 'total' (план против ФЭО целиком, владелец 07.10.2026) — своих
               слов в METRIC_FIELDS нет (та карта только для 4 видов по типу,
               см. useExcessDrilldown.ts), подписи «план»/«ФЭО» прямо тут. -->
          <span class="excess-bar__list-amounts" v-if="excessDrilldown.activeKind.value === 'total'">
            план {{ formatCurrency(row.upper) }} · ФЭО {{ formatCurrency(row.lower) }}
            <template v-if="row.excess > 0.005"> · превышение {{ formatCurrency(row.excess) }}</template>
          </span>
          <span class="excess-bar__list-amounts" v-else-if="excessDrilldown.activeMetric.value">
            {{ excessDrilldown.activeMetric.value.upperWord }} по {{ excessDrilldown.activeMetric.value.typeWord }} {{ formatCurrency(row.upper) }}
            · {{ excessDrilldown.activeMetric.value.lowerWord }} по {{ excessDrilldown.activeMetric.value.typeWord }} {{ formatCurrency(row.lower) }}
            <template v-if="row.excess > 0.005"> · превышение {{ formatCurrency(row.excess) }}</template>
          </span>
        </div>
      </div>
    </div>

    <!-- Строка управления — отдельно от текста (см. докстринг выше),
         всегда на виду, не часть переноса длинного текста. -->
    <div v-if="excessDrilldown.hasTargets.value" class="excess-bar__controls">
      <v-btn icon size="x-small" variant="text" @click="excessDrilldown.prev()"><v-icon icon="mdi-chevron-left" /></v-btn>
      <span class="excess-bar__counter">{{ excessDrilldown.currentIndex.value + 1 }} из {{ excessDrilldown.targets.value.length }}</span>
      <v-btn icon size="x-small" variant="text" @click="excessDrilldown.next()"><v-icon icon="mdi-chevron-right" /></v-btn>
      <v-btn size="x-small" variant="text" @click="listOpen = !listOpen">
        {{ listOpen ? 'скрыть список' : 'список статей' }}
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useExcessDrilldown } from '@/composables/subsidies/useExcessDrilldown'
import { formatCurrency } from '@/composables/subsidies/format'

const excessDrilldown = useExcessDrilldown()
const listOpen = ref(false)
</script>

<style scoped>
.excess-bar {
  position: fixed;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  /* Выше плавающей кнопки чата (App.vue, z-index:999) — приёмка 06.10.2026,
     дефект 1: на мобильном кнопка чата перекрывала текст/счётчик панели. */
  z-index: 1060;
  max-width: calc(100vw - 24px);
  background: #1f2937;
  color: #f3f4f6;
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.excess-bar__header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
}
.excess-bar__title {
  flex: 1 1 auto;
  min-width: 0;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.excess-bar__close { color: #f3f4f6; flex: 0 0 auto; }
/* Длинный текст/строка-разницы/список статей — своя прокручиваемая область,
   не толкает шапку/управляющую строку за экран (приёмка 06.10.2026, дефект
   1: ‹1 из 4›/✕ уезжали за пределы viewport при длинном тексте). */
.excess-bar__body {
  font-size: 12.5px;
  max-height: 45vh;
  overflow-y: auto;
}
.excess-bar__text {
  display: block;
  white-space: normal;
  word-break: break-word;
}
.excess-bar__controls {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
  white-space: nowrap;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  padding-top: 4px;
}
.excess-bar__controls .v-btn { color: #f3f4f6; }
.excess-bar__counter {
  font-weight: 600;
  min-width: 56px;
  text-align: center;
}
/* Дефект 3 приёмки — строка-разница «сумма статей ≠ сумма чипа». */
.excess-bar__diff {
  margin-top: 6px;
  font-size: 11.5px;
  color: #fdba74;
}
/* Приёмка 06.10.2026, desktop-дефект 2: раскрытый список статей закрывал
   нижнюю половину экрана — своя прокрутка с ограничением высоты, не растёт
   бесконечно вместе с .excess-bar__body. */
.excess-bar__list {
  margin-top: 6px;
  max-height: 35vh;
  overflow-y: auto;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  padding-top: 6px;
}
.excess-bar__list-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 5px 6px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.excess-bar__list-item:hover {
  background: rgba(255, 255, 255, 0.08);
}
.excess-bar__list-item--current {
  background: rgba(251, 146, 60, 0.28);
}
.excess-bar__list-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.excess-bar__list-amounts {
  font-size: 11px;
  opacity: 0.85;
}

/* Мобильная ширина — тот же порог и то же "высота bottom-nav + safe-area",
   что CookieBanner.vue (frontend/src/components/legal/CookieBanner.vue,
   .cookie-banner в @media max-width:959.98px) переиспользует над тем же
   AppBar.vue :: .mobile-bottom-nav (высота calc(60px + env(safe-area-inset-
   bottom)), z-index:2000) — иначе панель рисуется ПОД таб-баром и обрезает
   ‹N из M›/✕ (приёмка 06.10.2026, дефект 1). Второй копии «60px» не заводим
   — тот же источник, тот же порог брейкпоинта (Vuetify `mobile` в AppBar.vue
   v-if="mobile" тоже срабатывает <960px). */
@media (max-width: 959.98px) {
  .excess-bar {
    left: 8px;
    right: 8px;
    bottom: calc(60px + env(safe-area-inset-bottom, 0px) + 8px);
    transform: none;
    max-width: none;
  }
  .excess-bar__body {
    max-height: 45vh;
  }
  .excess-bar__list {
    max-height: 30vh;
  }
}
</style>
