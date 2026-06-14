<template>
  <v-dialog v-model="show" max-width="720" scrollable :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold px-4 pt-4 d-flex align-center">
        Создать ежемесячные этапы
        <v-spacer />
        <span class="text-body-2 text-medium-emphasis font-weight-regular">{{ contractName }}</span>
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-2" @click="show = false" />
      </v-card-title>

      <v-card-text class="px-4 pb-2">
        <v-alert v-if="errorMsg" type="error" variant="tonal" density="compact" class="mb-3">{{ errorMsg }}</v-alert>

        <v-row dense>
          <!-- Количество этапов -->
          <v-col cols="12" md="4">
            <v-text-field
              v-model.number="form.count"
              label="Кол-во этапов (1–36)"
              type="number" min="1" max="36"
              variant="outlined" density="compact"
            />
          </v-col>

          <!-- Сумма за этап -->
          <v-col cols="12" md="4">
            <v-text-field
              v-model.number="form.amountPerStage"
              label="Сумма за этап, ₽ *"
              type="number" min="0"
              variant="outlined" density="compact"
            />
          </v-col>

          <!-- Начальный год и месяц -->
          <v-col cols="6" md="2">
            <v-text-field
              v-model.number="form.startYear"
              label="Год"
              type="number" min="2020" max="2040"
              variant="outlined" density="compact"
            />
          </v-col>
          <v-col cols="6" md="2">
            <v-select
              v-model="form.startMonth"
              :items="monthItems"
              item-title="label" item-value="value"
              label="Месяц"
              variant="outlined" density="compact"
            />
          </v-col>

          <!-- Тип даты дедлайна -->
          <v-col cols="12">
            <v-radio-group v-model="form.deadlineKind" inline density="compact" hide-details class="mt-0">
              <v-radio label="Последний день месяца" value="end_of_month" />
              <v-radio label="Указанный день" value="specific_day" />
            </v-radio-group>
          </v-col>

          <!-- День (только при specific_day) -->
          <v-col v-if="form.deadlineKind === 'specific_day'" cols="12" md="3">
            <v-text-field
              v-model.number="form.deadlineDay"
              label="День (1–31)"
              type="number" min="1" max="31"
              variant="outlined" density="compact"
            />
          </v-col>

          <!-- Шаблон названия -->
          <v-col cols="12">
            <v-text-field
              v-model="form.subjectTemplate"
              label="Шаблон названия"
              variant="outlined" density="compact"
              hint="Переменные: {contract_name}, {month_name}, {year}"
              persistent-hint
            />
          </v-col>

          <!-- Скорее всего понадобится -->
          <v-col cols="12">
            <v-checkbox
              v-model="form.isLikelyNeeded"
              label="Скорее всего понадобится"
              density="compact" hide-details
            />
          </v-col>
        </v-row>

        <!-- Превью таблицей -->
        <div class="mt-4">
          <div class="text-body-2 font-weight-medium mb-2">Превью этапов</div>
          <v-table density="compact">
            <thead>
              <tr>
                <th>#</th>
                <th>Месяц</th>
                <th>Дедлайн</th>
                <th>Название</th>
                <th>Подпись этапа</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, idx) in previewItems" :key="idx">
                <td>{{ idx + 1 }}</td>
                <td>{{ item.stageLabel }}</td>
                <td>{{ item.deadlineStr }}</td>
                <td class="text-caption">{{ item.subject }}</td>
                <td class="text-caption">{{ item.stageLabel }}</td>
              </tr>
              <tr v-if="form.count > 12">
                <td colspan="5" class="text-caption text-medium-emphasis text-center py-2">
                  ... ещё {{ form.count - 12 }} этапов
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-card-text>

      <v-card-actions class="px-4 pb-3">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Отмена</v-btn>
        <v-btn
          color="primary" variant="tonal"
          :loading="saving"
          :disabled="!form.amountPerStage || form.count < 1"
          @click="doCreate"
        >
          Создать {{ form.count }} этапов
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'

const { mobile } = useDisplay()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  contractId: { type: Number, required: true },
  contractName: { type: String, default: '' },
  contractType: { type: String, default: '' },
  defaultSubsidyId: { type: Number as () => number | null, default: null },
  defaultAmount: { type: Number as () => number | null, default: null },
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created', payload: any): void
}>()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const now = new Date()
const curYear = now.getFullYear()
const curMonth = now.getMonth() + 1 // 1-based

// Next month (wrap to next year)
const defaultStartMonth = curMonth === 12 ? 1 : curMonth + 1
const defaultStartYear = curMonth === 12 ? curYear + 1 : curYear

const form = ref({
  count: 12,
  amountPerStage: props.defaultAmount ?? 0,
  startYear: defaultStartYear,
  startMonth: defaultStartMonth,
  deadlineKind: 'end_of_month' as 'end_of_month' | 'specific_day',
  deadlineDay: 15,
  subjectTemplate: '{contract_name} — {month_name} {year}',
  isLikelyNeeded: true,
})

// Re-init amountPerStage when defaultAmount changes
watch(() => props.defaultAmount, (v) => {
  if (v != null && form.value.amountPerStage === 0) form.value.amountPerStage = v
})

const saving = ref(false)
const errorMsg = ref('')

// Month items for v-select
const monthItems = [
  { value: 1, label: 'Январь' },
  { value: 2, label: 'Февраль' },
  { value: 3, label: 'Март' },
  { value: 4, label: 'Апрель' },
  { value: 5, label: 'Май' },
  { value: 6, label: 'Июнь' },
  { value: 7, label: 'Июль' },
  { value: 8, label: 'Август' },
  { value: 9, label: 'Сентябрь' },
  { value: 10, label: 'Октябрь' },
  { value: 11, label: 'Ноябрь' },
  { value: 12, label: 'Декабрь' },
]

// Родительный падеж месяцев для субъекта
const MONTH_GENITIVE = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

// Именительный для stage_label
const MONTH_NOMINATIVE = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

function lastDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function calcDeadline(year: number, month: number): string {
  if (form.value.deadlineKind === 'end_of_month') {
    const d = lastDayOfMonth(year, month)
    return `${String(d).padStart(2, '0')}.${String(month).padStart(2, '0')}.${year}`
  } else {
    const maxDay = lastDayOfMonth(year, month)
    const day = Math.min(form.value.deadlineDay, maxDay)
    return `${String(day).padStart(2, '0')}.${String(month).padStart(2, '0')}.${year}`
  }
}

function calcIsoDeadline(year: number, month: number): string {
  if (form.value.deadlineKind === 'end_of_month') {
    const d = lastDayOfMonth(year, month)
    return `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  } else {
    const maxDay = lastDayOfMonth(year, month)
    const day = Math.min(form.value.deadlineDay, maxDay)
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  }
}

function buildSubject(year: number, month: number): string {
  const monthName = MONTH_GENITIVE[month - 1]
  return form.value.subjectTemplate
    .replace('{contract_name}', props.contractName)
    .replace('{month_name}', monthName)
    .replace('{year}', String(year))
}

interface PreviewItem {
  year: number
  month: number
  deadlineStr: string
  subject: string
  stageLabel: string
}

const previewItems = computed((): PreviewItem[] => {
  const count = Math.min(form.value.count, 12)
  const items: PreviewItem[] = []
  let y = form.value.startYear
  let m = form.value.startMonth
  for (let i = 0; i < count; i++) {
    items.push({
      year: y,
      month: m,
      deadlineStr: calcDeadline(y, m),
      subject: buildSubject(y, m),
      stageLabel: `${MONTH_NOMINATIVE[m - 1]} ${y}`,
    })
    m++
    if (m > 12) { m = 1; y++ }
  }
  return items
})

async function doCreate() {
  errorMsg.value = ''
  saving.value = true
  try {
    const body = {
      count: form.value.count,
      amount_per_stage: form.value.amountPerStage,
      start_year: form.value.startYear,
      start_month: form.value.startMonth,
      deadline_kind: form.value.deadlineKind,
      deadline_day: form.value.deadlineDay,
      subject_template: form.value.subjectTemplate,
      subsidy_id: props.defaultSubsidyId ?? null,
      is_likely_needed: form.value.isLikelyNeeded,
    }
    const res = await apiFetch<any>(`/contracts/${props.contractId}/generate-monthly-stages`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    emit('created', res)
    show.value = false
  } catch (e: any) {
    errorMsg.value = e?.detail || e?.message || 'Ошибка создания этапов'
  } finally {
    saving.value = false
  }
}
</script>
