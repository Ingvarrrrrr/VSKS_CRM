<template>
  <!-- 9. Подпись водителя -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon color="primary" size="18">mdi-draw</v-icon>
      <span>Подпись водителя</span>
    </div>
    <div class="wbf-signature-wrap">
      <SignaturePad
        v-model="form.driver_signature"
        :readonly="form.status === 'closed' || form.status === 'on_review'"
        :width="480"
        :height="140"
      />
    </div>
    <div class="wbf-mt">
      <v-btn
        v-if="form.id && form.status === 'in_progress'"
        color="primary"
        :loading="signingLoading"
        prepend-icon="mdi-send"
        @click="$emit('driver-sign')"
      >
        Сдать путевой
      </v-btn>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import SignaturePad from '@/components/fleet/SignaturePad.vue'
import type { WaybillForm } from '@/composables/fleet/waybill/waybillFormTypes'

defineProps<{
  form: WaybillForm
  signingLoading: boolean
}>()
defineEmits<{
  (e: 'driver-sign'): void
}>()
</script>

<style scoped></style>
