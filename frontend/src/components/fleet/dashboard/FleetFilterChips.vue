<template>
  <div class="fleet-filters">
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'all' }"
      @click="$emit('update:activeFilter', 'all')"
    >
      Все <span class="fleet-chip__count">{{ filterCounts.all }}</span>
    </button>
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'working' }"
      @click="$emit('update:activeFilter', 'working')"
    >
      <i class="fleet-chip__dot fleet-chip__dot--ok"></i>
      Рабочие {{ filterCounts.working }}
    </button>
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'in_repair' }"
      @click="$emit('update:activeFilter', 'in_repair')"
    >
      <i class="fleet-chip__dot fleet-chip__dot--warn"></i>
      В ремонте {{ filterCounts.in_repair }}
    </button>
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'not_running' }"
      @click="$emit('update:activeFilter', 'not_running')"
    >
      <i class="fleet-chip__dot fleet-chip__dot--alert"></i>
      Не на ходу {{ filterCounts.not_running }}
    </button>
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'no_report' }"
      @click="$emit('update:activeFilter', 'no_report')"
    >
      <i class="fleet-chip__dot fleet-chip__dot--info"></i>
      Без отчёта 30+ дн.
    </button>
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'disposal' }"
      @click="$emit('update:activeFilter', 'disposal')"
    >
      <i class="fleet-chip__dot fleet-chip__dot--muted"></i>
      На списание {{ filterCounts.for_disposal }}
    </button>
    <button
      class="fleet-chip"
      :class="{ 'fleet-chip--active': activeFilter === 'docs_expiring' }"
      @click="$emit('update:activeFilter', 'docs_expiring')"
    >
      <i class="fleet-chip__dot fleet-chip__dot--alert"></i>
      Документы {{ maintenanceWarningsCount }}
    </button>

    <div class="fleet-filters__spacer"></div>

    <div v-if="!mobile" class="fleet-view-toggle">
      <button
        :class="{ active: viewMode === 'cards' }"
        @click="$emit('update:viewMode', 'cards')"
      >Карточки</button>
      <button
        :class="{ active: viewMode === 'table' }"
        @click="$emit('update:viewMode', 'table')"
      >Таблица</button>
      <button
        :class="{ active: viewMode === 'regions' }"
        @click="$emit('update:viewMode', 'regions')"
      >По регионам</button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  activeFilter: string
  filterCounts: { all: number; working: number; in_repair: number; not_running: number; no_report_30d: number; for_disposal: number }
  maintenanceWarningsCount: number
  mobile: boolean
  viewMode: 'cards' | 'table' | 'regions'
}>()

defineEmits<{
  (e: 'update:activeFilter', value: string): void
  (e: 'update:viewMode', value: 'cards' | 'table' | 'regions'): void
}>()
</script>

<style scoped></style>
