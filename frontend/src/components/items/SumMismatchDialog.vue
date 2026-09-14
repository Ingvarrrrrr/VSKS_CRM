<template>
  <v-dialog v-model="show" max-width="820" scrollable persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center gap-2 px-4 pt-4">
        <v-icon icon="mdi-calculator-variant-outline" color="warning" />
        Сумма не сходится с кол-во × цена
      </v-card-title>
      <v-card-subtitle class="px-4 pb-2 text-medium-emphasis">
        {{ warnings.length }} {{ rowWord }} файла, где сумма не равна количеству, умноженному на цену.
        Выберите, что оставить в каждой строке.
      </v-card-subtitle>
      <v-divider />
      <v-card-text class="pa-4">
        <div
          v-for="w in localWarnings"
          :key="w.row"
          class="mb-4 pa-3 rounded"
          style="border: 1px solid rgba(0,0,0,0.12)"
        >
          <div class="text-body-2 font-weight-medium mb-1">
            <v-chip size="x-small" class="mr-2" color="warning" variant="tonal">Строка {{ w.row }}</v-chip>
            {{ w.name }}
          </div>
          <div class="text-caption text-medium-emphasis mb-2">{{ w.message }}</div>
          <v-radio-group v-model="w._choice" inline density="compact" hide-details>
            <v-radio value="recalc_sum" color="primary">
              <template #label>
                <span>Пересчитать сумму = кол-во × цена ({{ fmt(w.calc_total) }})</span>
              </template>
            </v-radio>
            <v-radio value="recalc_price" color="primary">
              <template #label>
                <span>Пересчитать цену = сумма / кол-во</span>
              </template>
            </v-radio>
            <v-radio value="keep" color="grey">
              <template #label>
                <span>Оставить как в файле ({{ fmt(w.file_total) }})</span>
              </template>
            </v-radio>
          </v-radio-group>
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-btn variant="tonal" @click="setAll('recalc_sum')">Пересчитать сумму везде</v-btn>
        <v-btn variant="text" color="grey" @click="setAll('keep')">Оставить все как в файле</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="elevated" @click="onConfirm">Применить и продолжить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'

const { mobile } = useDisplay()

export interface SumMismatchWarning {
  kind: string
  row: number
  name: string
  message: string
  file_total: number
  calc_total: number
}

export type SumMismatchChoice = 'recalc_sum' | 'recalc_price' | 'keep'

const props = defineProps<{
  modelValue: boolean
  warnings: SumMismatchWarning[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** row (номер строки файла) → выбор пользователя */
  (e: 'confirm', resolutions: Record<number, SumMismatchChoice>): void
}>()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// Местная копия — по умолчанию «оставить как в файле» (владелец: «молча ничего
// не менять», см. диалог дублей DuplicateMergeDialog.vue — тот же стиль).
const localWarnings = ref<(SumMismatchWarning & { _choice: SumMismatchChoice })[]>([])

watch(
  () => props.warnings,
  (warnings) => {
    localWarnings.value = warnings.map((w) => ({ ...w, _choice: 'keep' as SumMismatchChoice }))
  },
  { immediate: true },
)

const rowWord = computed(() => {
  const n = props.warnings.length
  if (n === 1) return 'строка'
  if (n >= 2 && n <= 4) return 'строки'
  return 'строк'
})

function fmt(v: number): string {
  return Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function setAll(choice: SumMismatchChoice) {
  localWarnings.value.forEach((w) => (w._choice = choice))
}

function onConfirm() {
  const resolutions: Record<number, SumMismatchChoice> = {}
  for (const w of localWarnings.value) resolutions[w.row] = w._choice
  emit('confirm', resolutions)
  show.value = false
}
</script>
