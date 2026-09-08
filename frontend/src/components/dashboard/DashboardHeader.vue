<template>
  <div class="dash-header">
    <div class="dash-header-left">
      <v-icon icon="mdi-view-dashboard-outline" size="34" color="#fb923c" class="mr-3" />
      <div>
        <div class="dash-title gradient-text">Дашборд</div>
        <div class="dash-subtitle">GALA · Управление закупками · {{ selectedYear }}</div>
      </div>
    </div>
    <div class="dash-header-right">
      <v-chip-group v-model="selectedYear" mandatory class="year-chips">
        <v-chip
          v-for="year in availableYears" :key="year" :value="year"
          filter variant="elevated" color="primary" size="small"
        >{{ year }}</v-chip>
      </v-chip-group>
      <v-select
        v-model="selectedSubsidyIds"
        :items="allSubsidies.filter((s: any) => s.year === selectedYear)"
        item-title="name" item-value="id"
        label="Субсидии"
        variant="outlined" multiple chips clearable density="compact"
        style="min-width: 220px; max-width: 340px;"
        hide-details class="ml-3"
      />
      <v-btn
        v-if="!mobile"
        :icon="isEditing ? 'mdi-lock-open' : 'mdi-cursor-move'"
        :variant="isEditing ? 'flat' : 'tonal'"
        :color="isEditing ? 'warning' : 'default'"
        size="small" class="ml-3"
        @click="$emit('toggle-editing')"
        :title="isEditing ? 'Завершить редактирование' : 'Настроить расположение'"
      />
      <v-btn
        v-if="isEditing && !mobile"
        icon="mdi-restore" variant="tonal" color="error"
        size="small" class="ml-1"
        @click="$emit('reset-layout')"
        title="Сбросить расположение"
      />
      <v-btn
        icon="mdi-refresh" variant="tonal" color="primary"
        :loading="loading" @click="$emit('refresh')" size="small" class="ml-3"
      />
      <v-chip-group
        v-model="dashboardToggleMode"
        mandatory class="ml-3"
        selected-class="text-primary"
      >
        <v-chip value="classic" size="small" variant="outlined" prepend-icon="mdi-view-dashboard" style="min-height: 44px">
          Классик
        </v-chip>
        <v-chip value="radar" size="small" variant="outlined" prepend-icon="mdi-radar" style="min-height: 44px">
          Радар
        </v-chip>
      </v-chip-group>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  availableYears: number[]
  allSubsidies: any[]
  isEditing: boolean
  mobile: boolean
  loading: boolean
}>()

defineEmits<{
  (e: 'toggle-editing'): void
  (e: 'reset-layout'): void
  (e: 'refresh'): void
}>()

const selectedYear = defineModel<number>('selectedYear', { required: true })
const selectedSubsidyIds = defineModel<number[]>('selectedSubsidyIds', { required: true })
const dashboardToggleMode = defineModel<'classic' | 'radar'>('dashboardToggleMode', { required: true })
</script>
