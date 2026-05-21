<template>
  <v-dialog v-model="show" max-width="1100" persistent scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4 pb-2">
        <v-icon start color="primary">mdi-link-variant</v-icon>
        Сопоставление товаров с каталогом
        <v-spacer />
        <span class="text-caption text-medium-emphasis">
          Авто: {{ autoCount }} · Подтверждение: {{ suggestCount }} · Создать: {{ createCount }}
        </span>
        <v-btn icon="mdi-close" variant="text" @click="cancel" />
      </v-card-title>
      <v-card-text class="pa-4">
        <!-- Section 1: Auto-matched (collapsed by default) -->
        <v-expansion-panels v-model="openPanels" multiple variant="accordion" class="mb-3">
          <v-expansion-panel value="auto" v-if="autoRows.length">
            <v-expansion-panel-title>
              <v-icon color="success" start>mdi-check-decagram</v-icon>
              Авто-распознано ({{ autoRows.length }})
              <v-chip size="x-small" color="success" variant="tonal" class="ml-2">≥95%</v-chip>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-table density="compact">
                <thead><tr><th>Из файла</th><th>Совпадение в каталоге</th><th class="text-right">Score</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in autoRows" :key="i">
                    <td class="text-caption">{{ r.query }}</td>
                    <td class="text-caption">{{ r.candidates[0]?.name }}</td>
                    <td class="text-right"><v-chip size="x-small" color="success" variant="tonal">{{ Math.round((r.candidates[0]?.score || 0) * 100) }}%</v-chip></td>
                  </tr>
                </tbody>
              </v-table>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <!-- Section 2: Suggest — needs confirmation -->
          <v-expansion-panel value="suggest" v-if="suggestRows.length">
            <v-expansion-panel-title>
              <v-icon color="warning" start>mdi-help-circle-outline</v-icon>
              Требует подтверждения ({{ suggestRows.length }})
              <v-chip size="x-small" color="warning" variant="tonal" class="ml-2">60-95%</v-chip>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div v-for="(r, idx) in suggestRows" :key="idx" class="mb-3 pa-2 rounded" style="border:1px solid rgba(0,0,0,0.08)">
                <div class="text-body-2 font-weight-medium mb-1">{{ r.query }}</div>
                <v-radio-group v-model="r._choice" hide-details density="compact" class="ml-2">
                  <v-radio v-for="c in r.candidates" :key="c.product_id" :value="c.product_id">
                    <template #label>
                      <span class="text-caption">{{ c.name }}</span>
                      <v-chip size="x-small" :color="c.score >= 0.8 ? 'success' : 'warning'" variant="tonal" class="ml-2">
                        {{ Math.round(c.score * 100) }}%
                      </v-chip>
                    </template>
                  </v-radio>
                  <v-radio value="__create__">
                    <template #label>
                      <span class="text-caption text-primary"><v-icon size="14">mdi-plus</v-icon> Создать новый «{{ r.query }}»</span>
                    </template>
                  </v-radio>
                </v-radio-group>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <!-- Section 3: Will be created -->
          <v-expansion-panel value="create" v-if="createRows.length">
            <v-expansion-panel-title>
              <v-icon color="primary" start>mdi-plus-circle-outline</v-icon>
              Будут созданы в каталоге ({{ createRows.length }})
              <v-chip size="x-small" color="primary" variant="tonal" class="ml-2">не найдены</v-chip>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-table density="compact">
                <thead><tr><th>Имя</th><th class="text-right">Действие</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in createRows" :key="i">
                    <td class="text-caption">{{ r.query }}</td>
                    <td class="text-right">
                      <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-magnify"
                             @click="searchManual(r)">Найти в каталоге</v-btn>
                    </td>
                  </tr>
                </tbody>
              </v-table>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <v-btn variant="text" @click="cancel">Отменить импорт</v-btn>
        <v-btn color="primary" variant="elevated" :disabled="!canConfirm" @click="confirm">
          Применить сопоставление ({{ totalReady }} строк)
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

interface Candidate { product_id: number; name: string; price: number | null; score: number }
interface MatchRow { query: string; status: 'auto' | 'suggest' | 'create'; candidates: Candidate[]; _choice?: number | '__create__' | null }

const props = defineProps<{ modelValue: boolean; rows: MatchRow[] }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', resolved: Array<{query: string; product_id: number | null; create_new: boolean}>): void
  (e: 'cancel'): void
}>()

const show = computed({ get: () => props.modelValue, set: v => emit('update:modelValue', v) })
const openPanels = ref<string[]>(['suggest'])  // suggest по умолчанию открыт

const autoRows = computed(() => props.rows.filter(r => r.status === 'auto'))
const suggestRows = computed(() => props.rows.filter(r => r.status === 'suggest'))
const createRows = computed(() => props.rows.filter(r => r.status === 'create'))

const autoCount = computed(() => autoRows.value.length)
const suggestCount = computed(() => suggestRows.value.length)
const createCount = computed(() => createRows.value.length)

// Инициализируем _choice для suggest строк топ-кандидатом
watch(() => props.rows, (rows) => {
  for (const r of rows) {
    if (r.status === 'suggest' && r._choice === undefined) {
      r._choice = r.candidates[0]?.product_id ?? '__create__'
    }
  }
}, { immediate: true, deep: true })

const canConfirm = computed(() => suggestRows.value.every(r => r._choice != null))
const totalReady = computed(() => autoCount.value + suggestCount.value + createCount.value)

function searchManual(_r: MatchRow) { /* TODO: open product picker — пока no-op */ }

function confirm() {
  const resolved = props.rows.map(r => ({
    query: r.query,
    product_id: r.status === 'auto' ? r.candidates[0].product_id
              : r.status === 'suggest' && r._choice !== '__create__' ? r._choice as number
              : null,
    create_new: r.status === 'create' || r._choice === '__create__',
  }))
  emit('confirm', resolved)
  show.value = false
}

function cancel() { emit('cancel'); show.value = false }
</script>
