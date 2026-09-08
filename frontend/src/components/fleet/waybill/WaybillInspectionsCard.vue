<template>
  <!-- 7/8. Пред- и послерейсовые осмотры (общий шаблон для phase=pre|post) -->
  <v-card class="wbf-card" flat border>
    <div class="wbf-card-header">
      <v-icon :color="iconColor" size="18">{{ icon }}</v-icon>
      <span>{{ title }}</span>
    </div>
    <div class="wbf-inspections">
      <InspectionBlock
        kind="mechanic"
        :phase="phase"
        v-model:inspector-id="mechanicIdModel"
        v-model:inspected-at="mechanicAtModel"
        v-model:result="mechanicResultModel"
        :users="mechanicUsers"
        :readonly="readonly"
      />
      <InspectionBlock
        kind="doctor"
        :phase="phase"
        v-model:inspector-id="doctorIdModel"
        v-model:inspected-at="doctorAtModel"
        v-model:result="doctorResultModel"
        :users="doctorUsers"
        :readonly="readonly"
      />
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InspectionBlock from '@/components/fleet/InspectionBlock.vue'
import type { UserOption } from '@/composables/fleet/waybill/waybillFormTypes'

const props = defineProps<{
  phase: 'pre' | 'post'
  title: string
  icon: string
  iconColor: string
  mechanicId?: number
  mechanicAt?: string
  mechanicResult?: string
  doctorId?: number
  doctorAt?: string
  doctorResult?: string
  mechanicUsers: UserOption[]
  doctorUsers: UserOption[]
  readonly: boolean
}>()
const emit = defineEmits<{
  (e: 'update:mechanicId', v: number | undefined): void
  (e: 'update:mechanicAt', v: string | undefined): void
  (e: 'update:mechanicResult', v: string | undefined): void
  (e: 'update:doctorId', v: number | undefined): void
  (e: 'update:doctorAt', v: string | undefined): void
  (e: 'update:doctorResult', v: string | undefined): void
}>()

// Локальные writable-computed вместо прямых $emit в шаблоне — несколько
// разных литералов события у одного компонента ломают вывод типов у
// сгенерированного $emit (TS2769 "No overload matches this call").
const mechanicIdModel = computed({ get: () => props.mechanicId, set: (v: number | undefined) => emit('update:mechanicId', v) })
const mechanicAtModel = computed({ get: () => props.mechanicAt, set: (v: string | undefined) => emit('update:mechanicAt', v) })
const mechanicResultModel = computed({ get: () => props.mechanicResult, set: (v: string | undefined) => emit('update:mechanicResult', v) })
const doctorIdModel = computed({ get: () => props.doctorId, set: (v: number | undefined) => emit('update:doctorId', v) })
const doctorAtModel = computed({ get: () => props.doctorAt, set: (v: string | undefined) => emit('update:doctorAt', v) })
const doctorResultModel = computed({ get: () => props.doctorResult, set: (v: string | undefined) => emit('update:doctorResult', v) })
</script>

<style scoped></style>
