<template>
  <div class="wbf-topbar no-print">
    <div class="wbf-crumbs">
      <router-link to="/fleet">Автопарк</router-link>
      <span class="sep">/</span>
      <router-link to="/fleet/waybills">Путевые листы</router-link>
      <span class="sep">/</span>
      <span class="current">{{ isNew ? 'Новый' : `№ ${form.number}` }}</span>
    </div>
    <div class="wbf-topbar-center">
      <h1 class="wbf-title">{{ isNew ? 'Новый путевой лист' : `Путевой лист № ${form.number}` }}</h1>
      <StatusPill :variant="statusVariant(form.status)" :dot="form.status === 'in_progress'">
        {{ statusLabel(form.status) }}
      </StatusPill>
    </div>
    <div class="wbf-topbar-actions">
      <v-btn variant="outlined" size="small" prepend-icon="mdi-arrow-left" @click="router.back()">
        Назад
      </v-btn>
      <v-btn variant="outlined" size="small" prepend-icon="mdi-content-save-outline" :loading="saving" :disabled="isNew && !form.vehicle_id" @click="$emit('save-draft')">
        Сохранить черновик
      </v-btn>
      <v-btn
        v-if="form.id"
        variant="outlined"
        size="small"
        prepend-icon="mdi-download"
        :loading="downloadingDocx"
        @click="$emit('download-docx')"
      >
        Скачать .docx
      </v-btn>
      <!-- Phase 30.2: печать A5 (легковой) / A4 (грузовой), двусторонняя по длинной стороне -->
      <v-btn
        v-if="form.id"
        variant="outlined"
        size="small"
        prepend-icon="mdi-printer"
        @click="$emit('print')"
      >
        Распечатать
      </v-btn>
      <v-btn
        color="primary"
        size="small"
        :loading="saving"
        :disabled="isNew && !form.vehicle_id"
        @click="$emit('primary-action')"
      >
        {{ primaryActionLabel }}
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import StatusPill from '@/components/fleet/StatusPill.vue'
import { statusLabel, statusVariant } from '@/composables/fleet/waybill/useWaybillStatus'
import type { WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  isNew: boolean
  form: WaybillForm
  saving: boolean
  downloadingDocx: boolean
  primaryActionLabel: string
}>()
defineEmits<{
  (e: 'save-draft'): void
  (e: 'download-docx'): void
  (e: 'print'): void
  (e: 'primary-action'): void
}>()

const router = useRouter()
</script>

<style scoped></style>
