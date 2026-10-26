<template>
  <div>
    <div class="d-flex flex-wrap ga-2 align-center mb-2">
      <div class="text-subtitle-2">Характеристики каталога</div>
      <v-spacer v-if="!mobile" />
      <template v-if="!readonly">
        <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="addRow">Строка</v-btn>
        <v-btn size="small" variant="tonal" prepend-icon="mdi-format-list-bulleted" @click="addTypicalFields">Типовые поля</v-btn>
        <v-btn size="small" variant="tonal" prepend-icon="mdi-content-paste" @click="pasteDialog = true">Вставить с сайта</v-btn>
      </template>
    </div>

    <div v-if="readonly && !rows.length" class="text-caption text-medium-emphasis mb-2">
      Характеристик нет. Без права «Редактировать каталог товаров» заполнить их может любой —
      но карточка уже используется и правка здесь недоступна.
    </div>

    <div v-if="rows.length" class="pce-table-wrap">
      <table class="pce-table">
        <thead>
          <tr>
            <th>Параметр</th>
            <th>Значение</th>
            <th>Ед.</th>
            <th v-if="!readonly" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="idx">
            <td>
              <v-text-field v-model="row.name" density="compact" variant="outlined" hide-details
                :readonly="readonly" @update:model-value="emitUpdate" />
            </td>
            <td>
              <v-text-field v-model="row.value" density="compact" variant="outlined" hide-details
                :readonly="readonly" @update:model-value="emitUpdate" />
            </td>
            <td>
              <v-text-field v-model="row.unit" density="compact" variant="outlined" hide-details
                :readonly="readonly" @update:model-value="emitUpdate" />
            </td>
            <td v-if="!readonly">
              <v-btn icon size="small" variant="text" color="error" @click="removeRow(idx)">
                <v-icon size="18">mdi-delete-outline</v-icon>
              </v-btn>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <v-btn
      v-if="!readonly && rows.length"
      size="small" variant="tonal" color="secondary" class="mt-2"
      prepend-icon="mdi-text-box-check-outline"
      :loading="describing"
      @click="collectDescription"
    >
      Собрать точное описание из характеристик
    </v-btn>

    <!-- Вставка с сайта — текст → POST /characteristics/parse → предпросмотр
         строк → «Добавить»: совпадающие по имени (case-insensitive trim)
         обновляют value/unit существующей строки, остальные дописываются в
         конец (ПРАВИЛО №6 — тот же нормализатор парсинга, что вызывает этот
         диалог, второго не заводим). -->
    <v-dialog v-model="pasteDialog" max-width="560">
      <v-card>
        <v-card-title class="text-subtitle-1">Вставить характеристики с сайта</v-card-title>
        <v-card-text>
          <v-textarea
            v-model="pasteText" rows="8" auto-grow variant="outlined" density="compact"
            label="Скопируйте и вставьте сюда карточку товара с сайта поставщика"
          />
          <v-alert v-if="parseError" type="error" variant="tonal" density="comfortable" class="mt-2" closable @click:close="parseError = null">
            {{ parseError }}
          </v-alert>
          <div v-if="parsedPreview.length" class="mt-3">
            <div class="text-caption text-medium-emphasis mb-1">Распознано {{ parsedPreview.length }} характеристик:</div>
            <ul class="pce-preview-list">
              <li v-for="(p, i) in parsedPreview" :key="i">
                {{ p.name }}: {{ p.value }}{{ p.unit ? ' ' + p.unit : '' }}
              </li>
            </ul>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-btn variant="text" :loading="parsing" @click="runParse">Распознать</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closePasteDialog">Отмена</v-btn>
          <v-btn color="primary" :disabled="!parsedPreview.length" @click="applyParsed">Добавить</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import type { ProductCharacteristic } from '@/composables/products/productsTypes'

const props = defineProps<{
  modelValue: ProductCharacteristic[] | null
  readonly: boolean
  mobile?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: ProductCharacteristic[]): void
  // Карточка товара (ProductFormDialog.vue) вставляет текст в textarea
  // «Точное описание» — ЕДИНСТВЕННЫЙ сборщик текста build_tech_description
  // (ПРАВИЛО №6), этот компонент только зовёт preview-роутер и передаёт
  // готовый текст родителю, сам description не трогает.
  (e: 'description-generated', text: string): void
  (e: 'error', message: string): void
}>()

// Типовые поля (владелец, задача «ручное заполнение характеристик»,
// 26.10.2026) — дописывает ТОЛЬКО отсутствующие по имени, не трогает уже
// заполненные строки с тем же названием.
const TYPICAL_FIELDS: Array<{ name: string; unit?: string }> = [
  { name: 'Вес', unit: 'кг' },
  { name: 'Габариты Д×Ш×В', unit: 'см' },
  { name: 'Объём', unit: 'л' },
  { name: 'Материал' },
  { name: 'Цвет' },
  { name: 'Мощность', unit: 'Вт' },
  { name: 'Напряжение', unit: 'В' },
  { name: 'Страна производства' },
]

const rows = ref<ProductCharacteristic[]>(
  (props.modelValue || []).map(c => ({ name: c.name || '', value: c.value || '', unit: c.unit || '', in_description: c.in_description ?? true })),
)

// Родитель (useProductsForm.ts) подгружает characteristics отдельным
// запросом ПОСЛЕ открытия диалога (GET /products/{id}, список их не отдаёт) —
// локальная копия должна подхватить этот более поздний ответ.
watch(() => props.modelValue, (v) => {
  rows.value = (v || []).map(c => ({ name: c.name || '', value: c.value || '', unit: c.unit || '', in_description: c.in_description ?? true }))
})

function emitUpdate() {
  emit('update:modelValue', rows.value.map(r => ({ ...r })))
}

function addRow() {
  rows.value.push({ name: '', value: '', unit: '', in_description: true })
  emitUpdate()
}

function removeRow(idx: number) {
  rows.value.splice(idx, 1)
  emitUpdate()
}

function addTypicalFields() {
  const existing = new Set(rows.value.map(r => (r.name || '').trim().toLowerCase()))
  for (const f of TYPICAL_FIELDS) {
    if (existing.has(f.name.toLowerCase())) continue
    rows.value.push({ name: f.name, value: '', unit: f.unit || '', in_description: true })
  }
  emitUpdate()
}

// ---- Вставка с сайта -------------------------------------------------
const pasteDialog = ref(false)
const pasteText = ref('')
const parsing = ref(false)
const parseError = ref<string | null>(null)
const parsedPreview = ref<ProductCharacteristic[]>([])

function closePasteDialog() {
  pasteDialog.value = false
  pasteText.value = ''
  parsedPreview.value = []
  parseError.value = null
}

async function runParse() {
  parseError.value = null
  if (!pasteText.value.trim()) return
  parsing.value = true
  try {
    const res = await apiFetch<{ items: ProductCharacteristic[] }>('/products/characteristics/parse', {
      method: 'POST', body: { text: pasteText.value },
    })
    parsedPreview.value = res.items || []
    if (!parsedPreview.value.length) {
      parseError.value = 'Не удалось распознать ни одной характеристики — попробуйте другой формат (например, «Название: значение»).'
    }
  } catch (e: any) {
    parseError.value = describeApiError(e, { fallback: 'Не удалось разобрать текст', prefix: 'Ошибка' })
  } finally {
    parsing.value = false
  }
}

function applyParsed() {
  for (const p of parsedPreview.value) {
    const key = (p.name || '').trim().toLowerCase()
    const existingRow = rows.value.find(r => (r.name || '').trim().toLowerCase() === key)
    if (existingRow) {
      existingRow.value = p.value || ''
      existingRow.unit = p.unit || ''
    } else {
      rows.value.push({ name: p.name, value: p.value || '', unit: p.unit || '', in_description: true })
    }
  }
  emitUpdate()
  closePasteDialog()
}

// ---- Сбор описания из характеристик -----------------------------------
const describing = ref(false)

async function collectDescription() {
  describing.value = true
  try {
    const res = await apiFetch<{ text: string | null }>('/products/characteristics/describe', {
      method: 'POST',
      body: { characteristics: rows.value.filter(r => (r.name || '').trim() && (r.value || '').trim()) },
    })
    if (res.text) {
      emit('description-generated', res.text)
    } else {
      emit('error', 'Сформировать описание нельзя: заполните значения характеристик.')
    }
  } catch (e: any) {
    emit('error', describeApiError(e, { fallback: 'Не удалось собрать описание', prefix: 'Ошибка' }))
  } finally {
    describing.value = false
  }
}
</script>

<style scoped>
.pce-table-wrap { overflow-x: auto; }
.pce-table { width: 100%; min-width: 420px; border-collapse: collapse; }
.pce-table th { text-align: left; font-size: 12px; font-weight: 500; color: rgba(0,0,0,0.6); padding: 2px 4px; }
.pce-table td { padding: 2px 4px; vertical-align: top; }
.pce-preview-list { font-size: 13px; max-height: 160px; overflow-y: auto; margin: 0; padding-left: 18px; }
</style>
