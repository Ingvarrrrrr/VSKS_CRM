<template>
  <div>
    <div class="d-flex flex-wrap ga-2 align-center mb-2">
      <div class="text-subtitle-2">Характеристики каталога</div>
      <v-spacer v-if="!mobile" />
      <template v-if="!readonly">
        <v-btn
          size="small"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-web-sync"
          @click="openFetchDialog"
        >
          Загрузить с сайта
        </v-btn>
        <v-btn
          size="small"
          variant="tonal"
          prepend-icon="mdi-format-list-bulleted"
          @click="addTypicalFields"
        >
          Типовые поля
        </v-btn>
        <v-btn
          size="small"
          variant="tonal"
          prepend-icon="mdi-clipboard-text-outline"
          @click="pasteDialog = true"
        >
          Вставить текст
        </v-btn>
        <v-btn
          size="small"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="addRow"
        >
          Строка
        </v-btn>
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
            <th style="width: 45%;">Параметр</th>
            <th style="width: 35%;">Значение</th>
            <th style="width: 15%;">Ед.</th>
            <th v-if="!readonly" style="width: 5%;" />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="idx">
            <td>
              <v-text-field
                v-model="row.name"
                density="compact"
                variant="outlined"
                hide-details
                placeholder="Например, Вес"
                :readonly="readonly"
                @update:model-value="emitUpdate"
              />
            </td>
            <td>
              <v-text-field
                v-model="row.value"
                density="compact"
                variant="outlined"
                hide-details
                placeholder="Значение"
                :readonly="readonly"
                @blur="onValueBlur(row)"
                @update:model-value="emitUpdate"
              />
            </td>
            <td>
              <v-text-field
                v-model="row.unit"
                density="compact"
                variant="outlined"
                hide-details
                placeholder="кг / см / шт"
                :readonly="readonly"
                @update:model-value="emitUpdate"
              />
            </td>
            <td v-if="!readonly" class="text-center">
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
      size="small"
      variant="tonal"
      color="secondary"
      class="mt-2"
      prepend-icon="mdi-text-box-check-outline"
      :loading="describing"
      @click="collectDescription"
    >
      Собрать точное описание из характеристик
    </v-btn>

    <!-- Диалог 1: Автоматическая загрузка со страницы сайта по URL -->
    <v-dialog v-model="fetchDialog" max-width="620">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center ga-2">
          <v-icon color="primary">mdi-web-sync</v-icon>
          Загрузить характеристики с сайта поставщика
        </v-card-title>
        <v-card-text>
          <div class="text-body-2 text-medium-emphasis mb-3">
            Парсер автоматически скачает страницу товара, извлечёт таблицу параметров и строго разделит числовые значения и единицы измерения в разные поля.
          </div>

          <!-- Известные ссылки этого товара (из цен/источников) -->
          <div v-if="availableUrls.length" class="mb-3">
            <div class="text-caption text-medium-emphasis mb-1">Ссылки товара из базы:</div>
            <div class="d-flex flex-wrap ga-1">
              <v-chip
                v-for="(u, idx) in availableUrls"
                :key="idx"
                size="small"
                variant="tonal"
                :color="fetchUrl === u ? 'primary' : undefined"
                class="text-truncate"
                style="max-width: 100%; cursor: pointer;"
                @click="fetchUrl = u"
              >
                <v-icon start size="14">mdi-link-variant</v-icon>
                {{ formatUrlDisplay(u) }}
              </v-chip>
            </div>
          </div>

          <v-text-field
            v-model="fetchUrl"
            label="Ссылка на товар на сайте поставщика"
            placeholder="https://..."
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-web"
            clearable
            :error-messages="fetchError || ''"
            @keydown.enter="runFetch"
          />

          <div class="d-flex align-center justify-space-between mt-2 flex-wrap ga-2">
            <v-btn
              color="primary"
              variant="flat"
              prepend-icon="mdi-cloud-download-outline"
              :loading="fetching"
              :disabled="!fetchUrl?.trim()"
              @click="runFetch"
            >
              Загрузить данные
            </v-btn>
            <v-checkbox
              v-if="rows.length"
              v-model="replaceOnFetch"
              density="compact"
              hide-details
              label="Заменить существующие строки"
            />
          </div>

          <div v-if="fetchedPreview.length" class="mt-4 pa-3 border rounded bg-surface-variant">
            <div class="text-subtitle-2 font-weight-bold mb-2 text-success d-flex align-center ga-1">
              <v-icon size="18" color="success">mdi-check-circle-outline</v-icon>
              Распознано {{ fetchedPreview.length }} характеристик (значение и ед. разделены):
            </div>
            <div class="pce-preview-wrap">
              <table class="pce-preview-table">
                <thead>
                  <tr>
                    <th>Параметр</th>
                    <th>Значение</th>
                    <th>Ед.</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, i) in fetchedPreview" :key="i">
                    <td class="font-weight-medium">{{ p.name }}</td>
                    <td>{{ p.value }}</td>
                    <td class="text-primary font-weight-bold">{{ p.unit || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closeFetchDialog">Отмена</v-btn>
          <v-btn
            color="success"
            variant="elevated"
            :disabled="!fetchedPreview.length"
            @click="applyFetched"
          >
            Применить ({{ fetchedPreview.length }})
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Диалог 2: Вставка скопированного текста вручную из буфера обмена -->
    <v-dialog v-model="pasteDialog" max-width="560">
      <v-card>
        <v-card-title class="text-subtitle-1 d-flex align-center ga-2">
          <v-icon>mdi-clipboard-text-outline</v-icon>
          Вставить характеристики из текста
        </v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-2">
            Скопируйте блок характеристик со страницы сайта и вставьте ниже. Парсер распознает строки и отделит единицы измерения.
          </div>
          <v-textarea
            v-model="pasteText"
            rows="8"
            auto-grow
            variant="outlined"
            density="compact"
            placeholder="Вес: 0.1 кг&#10;Длина: 5 см&#10;Ширина: 10 см&#10;Высота: 2 см"
          />
          <v-alert
            v-if="parseError"
            type="error"
            variant="tonal"
            density="comfortable"
            class="mt-2"
            closable
            @click:close="parseError = null"
          >
            {{ parseError }}
          </v-alert>
          <div v-if="parsedPreview.length" class="mt-3">
            <div class="text-caption text-medium-emphasis mb-1">
              Распознано {{ parsedPreview.length }} характеристик:
            </div>
            <div class="pce-preview-wrap">
              <table class="pce-preview-table">
                <thead>
                  <tr>
                    <th>Параметр</th>
                    <th>Значение</th>
                    <th>Ед.</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, i) in parsedPreview" :key="i">
                    <td>{{ p.name }}</td>
                    <td>{{ p.value }}</td>
                    <td class="text-primary font-weight-bold">{{ p.unit || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-btn variant="text" :loading="parsing" @click="runParse">Распознать</v-btn>
          <v-spacer />
          <v-btn variant="text" @click="closePasteDialog">Отмена</v-btn>
          <v-btn
            color="primary"
            :disabled="!parsedPreview.length"
            @click="applyParsed"
          >
            Добавить
          </v-btn>
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
  sourceUrls?: string[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: ProductCharacteristic[]): void
  (e: 'description-generated', text: string): void
  (e: 'error', message: string): void
}>()

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

/**
 * Автоматически разделяет склеенное "0.1 кг" или "5 см" на значение и единицу.
 */
function splitValueUnit(value: string, unit: string | null | undefined): { value: string; unit: string } {
  const cleanUnit = (unit || '').trim()
  const cleanVal = (value || '').trim()
  if (cleanUnit) {
    return { value: cleanVal, unit: cleanUnit }
  }
  // Регулярка для "0.1 кг", "5 см", "220 В", "100 Вт", "280 ₽"
  const m = cleanVal.match(/^(-?\d+(?:[.,]\d+)?)\s+([^\d\s][^\n]*)$/)
  if (m) {
    const numPart = m[1].trim()
    const rest = m[2].trim()
    // Проверяем, что rest — короткая единица без знаков умножения
    if (!/[x×]/.test(rest) && rest.length <= 20) {
      return { value: numPart, unit: rest }
    }
  }
  return { value: cleanVal, unit: '' }
}

function normalizeIncomingRow(c: ProductCharacteristic): ProductCharacteristic {
  const { value, unit } = splitValueUnit(c.value || '', c.unit)
  return {
    name: c.name || '',
    value,
    unit,
    in_description: c.in_description ?? true,
  }
}

const rows = ref<ProductCharacteristic[]>(
  (props.modelValue || []).map(normalizeIncomingRow),
)

watch(() => props.modelValue, (v) => {
  rows.value = (v || []).map(normalizeIncomingRow)
})

function emitUpdate() {
  emit('update:modelValue', rows.value.map(r => ({ ...r })))
}

function onValueBlur(row: ProductCharacteristic) {
  if (!row.unit?.trim() && row.value?.trim()) {
    const res = splitValueUnit(row.value, row.unit)
    if (res.unit) {
      row.value = res.value
      row.unit = res.unit
      emitUpdate()
    }
  }
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

// ---- Автоматическая загрузка с сайта ---------------------------------
const fetchDialog = ref(false)
const fetchUrl = ref('')
const fetching = ref(false)
const fetchError = ref<string | null>(null)
const fetchedPreview = ref<ProductCharacteristic[]>([])
const replaceOnFetch = ref(false)

const availableUrls = computed(() => {
  const list = props.sourceUrls || []
  return list.filter(u => u && u.startsWith('http'))
})

function formatUrlDisplay(url: string): string {
  try {
    const u = new URL(url)
    const path = u.pathname.length > 25 ? u.pathname.slice(0, 25) + '…' : u.pathname
    return `${u.hostname}${path}`
  } catch {
    return url.slice(0, 35)
  }
}

function openFetchDialog() {
  fetchError.value = null
  fetchedPreview.value = []
  // Автоматически подставляем первую доступную ссылку товара
  if (!fetchUrl.value && availableUrls.value.length) {
    fetchUrl.value = availableUrls.value[0]
  }
  fetchDialog.value = true
}

function closeFetchDialog() {
  fetchDialog.value = false
  fetchError.value = null
  fetchedPreview.value = []
}

async function runFetch() {
  fetchError.value = null
  if (!fetchUrl.value?.trim()) return
  fetching.value = true
  try {
    const res = await apiFetch<{ items: ProductCharacteristic[] }>('/products/characteristics/fetch-from-url', {
      method: 'POST',
      body: { url: fetchUrl.value.trim() },
    })
    fetchedPreview.value = (res.items || []).map(normalizeIncomingRow)
    if (!fetchedPreview.value.length) {
      fetchError.value = 'На странице товара не удалось обнаружить таблицу характеристик.'
    }
  } catch (e: any) {
    fetchError.value = describeApiError(e, { fallback: 'Не удалось загрузить данные с сайта', prefix: 'Ошибка' })
  } finally {
    fetching.value = false
  }
}

function applyFetched() {
  if (replaceOnFetch.value) {
    rows.value = [...fetchedPreview.value]
  } else {
    for (const p of fetchedPreview.value) {
      const key = (p.name || '').trim().toLowerCase()
      const existingRow = rows.value.find(r => (r.name || '').trim().toLowerCase() === key)
      if (existingRow) {
        existingRow.value = p.value || ''
        existingRow.unit = p.unit || ''
      } else {
        rows.value.push({ ...p })
      }
    }
  }
  emitUpdate()
  closeFetchDialog()
}

// ---- Вставка из текста / буфера ---------------------------------------
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
    parsedPreview.value = (res.items || []).map(normalizeIncomingRow)
    if (!parsedPreview.value.length) {
      parseError.value = 'Не удалось распознать ни одной характеристики — попробуйте формат «Название: значение».'
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
.pce-table th { text-align: left; font-size: 12px; font-weight: 500; color: rgba(0,0,0,0.6); padding: 4px 6px; }
.pce-table td { padding: 3px 6px; vertical-align: top; }
.pce-preview-wrap { max-height: 200px; overflow-y: auto; }
.pce-preview-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.pce-preview-table th { text-align: left; padding: 3px 6px; border-bottom: 1px solid rgba(0,0,0,0.12); }
.pce-preview-table td { padding: 3px 6px; border-bottom: 1px solid rgba(0,0,0,0.06); }
</style>
