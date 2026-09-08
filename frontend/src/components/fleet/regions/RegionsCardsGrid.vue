<template>
  <h2 class="rv-section-title">
    Карточки по месту нахождения
    <span class="rv-section-title__sub">— распределение техники по месту нахождения, состояние парка</span>
  </h2>
  <section class="rv-cards-grid">
    <div v-if="loading" class="rv-loading" style="grid-column:1/-1">
      <div class="rv-spinner"></div>
    </div>
    <article
      v-else
      v-for="(loc, idx) in sortedLocations"
      :key="loc.region"
      class="rv-card"
      :class="[
        cardColorClassForLocation(idx),
        {
          'rv-card--match': searchActive && matchedRegions.has(loc.region),
          'rv-card--dim':   searchActive && !matchedRegions.has(loc.region),
        },
      ]"
    >
      <div class="rv-card__head">
        <div class="rv-card__flag" :class="cardColorClassForLocation(idx)">
          {{ locationAbbr(loc.region) }}
        </div>
        <div class="rv-card__title">
          <div class="rv-card__nm" :title="loc.region">{{ loc.region }}</div>
          <div v-if="locationSubtitle(loc.region)" class="rv-card__ds" :title="locationSubtitle(loc.region)">{{ locationSubtitle(loc.region) }}</div>
        </div>
        <div class="rv-card__big">
          {{ loc.count }}
          <small>единиц</small>
        </div>
      </div>

      <!-- Status chips. 2026-09 (владелец, дефект «сумма не сходится»): машины
           без заполненного Vehicle.state (у большинства мест — почти все,
           кроме донецких/курских) не попадали ни в один из трёх чипов и
           молча выпадали из подсчёта — 4-й чип делает их видимой категорией,
           а не «потерянными» машинами. Backend отдаёт их как by_state.unknown
           (см. vehicles_dashboard.py). -->
      <div class="rv-card__chips">
        <span class="rv-chip rv-chip--ok">
          {{ loc.by_state.working || 0 }} в работе
        </span>
        <span class="rv-chip rv-chip--warn">
          {{ (loc.by_state.in_repair || 0) + (loc.by_state.needs_repair || 0) }} в ремонте
        </span>
        <span class="rv-chip rv-chip--alert">
          {{ loc.by_state.broken || 0 }} сломано
        </span>
        <span class="rv-chip rv-chip--muted">
          {{ loc.by_state.unknown || 0 }} без состояния
        </span>
      </div>

      <!-- Details button -->
      <div class="rv-card__footer">
        <button class="rv-btn rv-btn--sm" style="margin-left:auto" @click.stop="$emit('select', loc.region)">
          Показать машины →
        </button>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import type { RegionItem } from '@/composables/fleet/regions/useRegionsData'
import { useLocationDisplay } from '@/composables/fleet/regions/useLocationDisplay'

defineProps<{
  loading: boolean
  sortedLocations: RegionItem[]
  searchActive: boolean
  matchedRegions: Set<string>
}>()

defineEmits<{
  (e: 'select', region: string): void
}>()

const { locationAbbr, locationSubtitle, cardColorClassForLocation } = useLocationDisplay()
</script>

<style scoped></style>
