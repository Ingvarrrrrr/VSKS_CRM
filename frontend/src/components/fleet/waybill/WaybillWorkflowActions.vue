<template>
  <!-- Workflow action buttons -->
  <div class="wbf-workflow-actions">
    <template v-if="form.id">
      <v-btn
        v-if="form.status === 'created'"
        color="warning"
        prepend-icon="mdi-wrench"
        :loading="actionLoading"
        @click="$emit('submit-tech-inspect')"
      >
        Передать механику
      </v-btn>
      <v-btn
        v-if="form.status === 'tech_inspect'"
        color="success"
        prepend-icon="mdi-check"
        :loading="actionLoading"
        @click="$emit('confirm-tech-inspect')"
      >
        Подтвердить тех. осмотр
      </v-btn>
      <v-btn
        v-if="form.status === 'med_inspect'"
        color="success"
        prepend-icon="mdi-medical-bag"
        :loading="actionLoading"
        @click="$emit('confirm-med-inspect')"
      >
        Подтвердить медосмотр
      </v-btn>
      <v-btn
        v-if="form.status === 'on_review'"
        color="primary"
        prepend-icon="mdi-archive-check"
        :loading="actionLoading"
        @click="$emit('close-waybill')"
      >
        Закрыть путевой лист
      </v-btn>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  actionLoading: boolean
}>()
defineEmits<{
  (e: 'submit-tech-inspect'): void
  (e: 'confirm-tech-inspect'): void
  (e: 'confirm-med-inspect'): void
  (e: 'close-waybill'): void
}>()
</script>

<style scoped></style>
