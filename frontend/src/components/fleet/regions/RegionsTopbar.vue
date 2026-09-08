<template>
  <div class="rv-topbar">
    <div>
      <div class="rv-crumbs">
        <router-link to="/fleet">Автопарк</router-link>
        <span class="rv-crumbs__sep">/</span>
        <b>Регионы и места нахождения</b>
      </div>
      <h1 class="rv-h1">География парка</h1>
      <p class="rv-lead">
        Распределение
        <b>{{ totalVehicles }}</b> единиц техники по
        <b>{{ locationsCount }}</b> местам нахождения ·
        клик по месту нахождения — список машин
      </p>
    </div>

    <!-- 2026-09 (владелец: «нужен поиск по автомобилю... как в Иерархии»):
         поиск по гос.№/марке/модели/VIN — сервер уже умеет это в GET /vehicles?q=
         (см. VehicleListView.vue), здесь просто переиспользуем эндпоинт. Найденные
         машины подсвечивают на карте кружок своего места нахождения (тот же приём,
         что hv-node-match/hv-node-dim в HierarchyView.vue) — состояние поиска
         владеет FleetRegionsView.vue (useVehicleSearch), сюда приходит пропсами,
         т.к. оно же нужно карте и карточкам для подсветки. -->
    <div class="rv-vsearch">
      <div class="rv-vsearch__box">
        <span class="rv-vsearch__ic">⌕</span>
        <input
          :value="query"
          type="text"
          class="rv-vsearch__input"
          placeholder="Поиск ТС: гос.№, марка, модель, VIN…"
          @input="$emit('update:query', ($event.target as HTMLInputElement).value)"
        />
        <button
          v-if="query"
          class="rv-vsearch__clear"
          title="Очистить"
          @click="$emit('update:query', '')"
        >✕</button>
        <span
          v-if="active"
          class="rv-vsearch__count"
          :class="matchCount ? 'rv-vsearch__count--ok' : 'rv-vsearch__count--zero'"
        >{{ loading ? '…' : (matchCount || 0) }}</span>
      </div>

      <!-- Результаты — краткий текстовый список, клик открывает попап места -->
      <div v-if="active" class="rv-vsearch__results">
        <div v-if="loading" class="rv-vsearch__hint">Ищем…</div>
        <template v-else-if="results.length">
          <div
            v-for="v in results"
            :key="v.id"
            class="rv-vsearch__row"
            @click="$emit('open-location', vehicleLocationRegion(v))"
          >
            <LicensePlate :modelValue="v.plate" size="sm" />
            <span class="rv-vsearch__row-nm">{{ [v.brand, v.model].filter(Boolean).join(' ') || '—' }}</span>
            <span class="rv-vsearch__row-sep">·</span>
            <span class="rv-vsearch__row-loc">{{ vehicleLocationRegion(v) }}</span>
          </div>
          <div v-if="hasMore" class="rv-vsearch__hint">
            показаны первые {{ results.length }} из {{ total }} — уточните запрос
          </div>
        </template>
        <div v-else class="rv-vsearch__hint rv-vsearch__hint--empty">
          Ничего не найдено по «{{ query.trim() }}»
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LicensePlate from '@/components/vehicles/LicensePlate.vue'
import type { VehicleSearchItem } from '@/composables/fleet/regions/useVehicleSearch'

defineProps<{
  totalVehicles: number
  locationsCount: number
  query: string
  results: VehicleSearchItem[]
  total: number
  loading: boolean
  active: boolean
  matchCount: number
  hasMore: boolean
  vehicleLocationRegion: (v: VehicleSearchItem) => string
}>()

defineEmits<{
  (e: 'update:query', value: string): void
  (e: 'open-location', region: string): void
}>()
</script>

<style scoped></style>
