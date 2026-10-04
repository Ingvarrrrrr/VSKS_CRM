<template>
  <v-dialog v-model="dialog" max-width="480" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="warning">mdi-calendar-alert</v-icon>
        Выберите месяц оказания
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
          {{ reason || 'Месяц оказания услуги по этой закупке не удалось определить автоматически.' }}
        </v-alert>
        <div class="text-body-2 text-medium-emphasis mb-3">
          Бэкенд не предложил список свободных месяцев — выберите месяц и год вручную.
        </div>
        <div class="d-flex gap-3">
          <v-select
            v-model="month"
            :items="monthItems"
            item-title="label"
            item-value="value"
            label="Месяц"
            variant="outlined"
            density="compact"
            hide-details
          />
          <v-select
            v-model="year"
            :items="yearItems"
            label="Год"
            variant="outlined"
            density="compact"
            hide-details
            style="max-width: 120px"
          />
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4 gap-2">
        <v-btn variant="text" @click="onCancel">Отмена</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="elevated" @click="onSubmit">Повторить с этим месяцем</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Задача 04.10.2026 («Помесячные платежи — разные месяцы»): новый компонент
// (ПРАВИЛО №5) — диалог ручного выбора месяца оказания после 409-конфликта от
// POST /payments/registry/{id}/confirm или POST /purchases/attach-payments
// (см. frontend/src/composables/payments/useServicePeriodConflict.ts). Бэк
// (app/services/payment_service_period.py) не отдаёт список свободных месяцев —
// только текст причины, поэтому выбор ручной: два v-select (месяц/год).
import { ref, computed, watch } from 'vue'

const props = defineProps<{
  reason?: string | null
}>()

const dialog = defineModel<boolean>({ default: false })

const emit = defineEmits<{
  (e: 'submit', isoFirstOfMonth: string): void
  (e: 'cancel'): void
}>()

const MONTH_LABELS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]
const monthItems = MONTH_LABELS.map((label, i) => ({ label, value: i + 1 }))

const now = new Date()
const month = ref<number>(now.getMonth() + 1)
const year = ref<number>(now.getFullYear())
const yearItems = computed(() => {
  const base = now.getFullYear()
  const years: number[] = []
  for (let y = base - 3; y <= base + 1; y++) years.push(y)
  return years
})

// При каждом открытии диалога (новый конфликт) — сброс на текущий месяц,
// чтобы старый выбор от прошлой попытки не подставился молча.
watch(dialog, (val) => {
  if (val) {
    month.value = now.getMonth() + 1
    year.value = now.getFullYear()
  }
})

function onSubmit() {
  const mm = String(month.value).padStart(2, '0')
  emit('submit', `${year.value}-${mm}-01`)
  dialog.value = false
}

function onCancel() {
  emit('cancel')
  dialog.value = false
}
</script>
