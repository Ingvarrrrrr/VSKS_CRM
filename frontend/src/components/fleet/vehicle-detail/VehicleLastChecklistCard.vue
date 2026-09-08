<!-- Последний чек-лист водителя (Slice 2). -->
<template>
  <v-card class="vp-box mb-4">
    <v-card-title class="vp-box__title">
      <v-icon icon="mdi-clipboard-check-outline" size="small" class="mr-2" />
      Последний чек-лист водителя
      <v-chip
        v-if="checklist"
        :color="overallStateColor(checklist.overall_state)"
        size="x-small"
        variant="tonal"
        class="ml-2"
      >{{ OVERALL_STATE_LABELS[checklist.overall_state ?? ''] ?? checklist.overall_state ?? '—' }}</v-chip>
      <span class="vp-box-sub ml-auto" v-if="checklist">{{ formatDate(checklist.created_at) }}</span>
    </v-card-title>
    <v-card-text>
      <div v-if="!checklist" class="text-medium-emphasis text-body-2 py-2">
        Чек-листов пока нет
      </div>
      <template v-else>
        <div class="vp-cl-grid">
          <div
            v-for="key in ['akb','tires','mirrors','radio','firstaid','extinguisher','spare','lkp']"
            :key="key"
            class="vp-cl-item"
            :class="checkItemClass(clItemStatus(checklist.items, key))"
          >
            <span class="vp-cl-label">{{ CHECKLIST_KEY_LABELS[key] }}</span>
            <span class="vp-cl-badge">
              <template v-if="clItemStatus(checklist.items, key) === 'ok'">✓</template>
              <template v-else-if="clItemStatus(checklist.items, key) === 'issue'">?</template>
              <template v-else>✗</template>
            </span>
          </div>
        </div>
        <div class="d-flex gap-2 flex-wrap mt-3">
          <v-chip v-if="checklist.fuel_level" size="small" variant="tonal" color="blue-grey">
            Топливо: {{ FUEL_LABELS[checklist.fuel_level] ?? checklist.fuel_level }}
          </v-chip>
          <v-chip v-if="checklist.paint_condition" size="small" variant="tonal" color="blue-grey">
            ЛКП: {{ checklist.paint_condition }}
          </v-chip>
        </div>
        <div v-if="checklist.notes" class="text-caption text-medium-emphasis mt-2">{{ checklist.notes }}</div>
      </template>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import type { Checklist } from '@/composables/fleet/vehicleDetailTypes'
import {
  CHECKLIST_KEY_LABELS,
  FUEL_LABELS,
  OVERALL_STATE_LABELS,
  checkItemClass,
  overallStateColor,
  clItemStatus,
} from '@/composables/fleet/useVehicleLastChecklist'

defineProps<{
  checklist: Checklist | null
  formatDate: (d?: string | null) => string
}>()
</script>
