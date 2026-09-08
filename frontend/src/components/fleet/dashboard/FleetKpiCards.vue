<template>
  <section class="fleet-kpis">
    <!-- Total -->
    <div
      class="fleet-kpi fleet-kpi--clickable"
      :class="{ 'fleet-kpi--active': activeFilter === 'all' && !selectedTypes.length && !selectedRegions.length && !searchQuery && !drillDocsOpen }"
      @click="$emit('reset-all')"
    >
      <div class="fleet-kpi__label">Всего в реестре</div>
      <div class="fleet-kpi__value">{{ kpi.total_vehicles }}</div>
      <div class="fleet-kpi__sub">авто, спецтехника, квадроциклы, прицепы</div>
      <div class="fleet-kpi__bar">
        <i style="width:100%;background:linear-gradient(90deg,#6aa6ff,#8b5cf6)"></i>
      </div>
    </div>
    <!-- Working -->
    <div class="fleet-kpi fleet-kpi--clickable" @click="$emit('apply-filter', 'working')">
      <div class="fleet-kpi__label">В рабочем</div>
      <div class="fleet-kpi__value">{{ filterCounts.working }}</div>
      <div class="fleet-kpi__trend fleet-kpi__trend--ok">+2 за неделю</div>
      <div class="fleet-kpi__sub">{{ workingPct }}% парка</div>
      <div class="fleet-kpi__bar">
        <i :style="`width:${workingPct}%;background:linear-gradient(90deg,#22c997,#5dd0ff)`"></i>
      </div>
    </div>
    <!-- In repair -->
    <div class="fleet-kpi fleet-kpi--clickable" @click="$emit('apply-filter', 'in_repair')">
      <div class="fleet-kpi__label">В ремонте</div>
      <div class="fleet-kpi__value">{{ filterCounts.in_repair }}</div>
      <div class="fleet-kpi__trend fleet-kpi__trend--warn">−1</div>
      <div class="fleet-kpi__sub">включая неисправные</div>
      <div class="fleet-kpi__bar">
        <i :style="`width:${repairPct}%;background:linear-gradient(90deg,#f6b34a,#ff8a4a)`"></i>
      </div>
    </div>
    <!-- Not running -->
    <div class="fleet-kpi fleet-kpi--clickable" @click="$emit('apply-filter', 'not_running')">
      <div class="fleet-kpi__label">Не на ходу / списать</div>
      <div class="fleet-kpi__value">{{ filterCounts.not_running }}</div>
      <div class="fleet-kpi__trend fleet-kpi__trend--alert">+3</div>
      <div class="fleet-kpi__sub">требует решения по эксплуатации</div>
      <div class="fleet-kpi__bar">
        <i :style="`width:${notRunningPct}%;background:linear-gradient(90deg,#ff5b6a,#ff3b8b)`"></i>
      </div>
    </div>
    <!-- Docs -->
    <div
      class="fleet-kpi fleet-kpi--clickable"
      :class="{ 'fleet-kpi--active': drillDocsOpen }"
      @click="$emit('open-docs-drill')"
    >
      <div class="fleet-kpi__label">Документы — истекли/истекают</div>
      <div class="fleet-kpi__value">{{ maintenanceWarningsCount }}</div>
      <div class="fleet-kpi__trend fleet-kpi__trend--alert">+2</div>
      <div class="fleet-kpi__sub">ОСАГО, ТО, СТС</div>
      <div class="fleet-kpi__bar">
        <i :style="`width:${docsPct}%;background:linear-gradient(90deg,#ff5b6a,#ff3b8b)`"></i>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  kpi: { total_vehicles: number; fuel_total_cost: number; repairs_total_cost: number; total_mileage_km: number }
  filterCounts: { all: number; working: number; in_repair: number; not_running: number; no_report_30d: number; for_disposal: number }
  workingPct: number
  repairPct: number
  notRunningPct: number
  docsPct: number
  activeFilter: string
  selectedTypes: string[]
  selectedRegions: string[]
  searchQuery: string
  drillDocsOpen: boolean
  maintenanceWarningsCount: number
}>()

defineEmits<{
  (e: 'reset-all'): void
  (e: 'apply-filter', stateCode: string): void
  (e: 'open-docs-drill'): void
}>()
</script>

<style scoped></style>
