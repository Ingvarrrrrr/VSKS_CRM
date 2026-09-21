<template>
  <v-dialog v-model="show" max-width="900" scrollable persistent :fullscreen="mobile">
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center gap-2 px-4 pt-4">
        <v-icon icon="mdi-content-duplicate" color="warning" />
        Обнаружены дублирующиеся позиции
      </v-card-title>
      <v-card-subtitle class="px-4 pb-2 text-medium-emphasis">
        <template v-if="mode === 'tz'">
          Найдено {{ groupCount }} {{ groupWord }} повторяющихся позиций ТЗ. Выберите, что сделать с каждой.
        </template>
        <template v-else>
          Найдено {{ groupCount }} {{ groupWord }} с несколькими строками с одним товаром. Выберите, что сделать с каждой.
        </template>
      </v-card-subtitle>
      <v-divider />
      <v-card-text class="pa-4">
        <!-- mode="items" (по умолчанию) — дубли товара внутри редактируемых позиций
             формы (PurchaseItemsEditor.vue), исходное поведение без изменений.
             v-if вынесен на обёртывающий <template> — на одном узле с v-for в
             Vue 3 v-if имеет приоритет и видит g/i ДО того, как v-for их создаст. -->
        <template v-if="mode !== 'tz'">
          <div
            v-for="(g, i) in localGroups"
            :key="g.product_id ?? i"
            class="mb-4 pa-3 rounded"
            style="border: 1px solid rgba(0,0,0,0.12)"
          >
            <div class="text-body-2 font-weight-medium mb-2">
              <v-icon icon="mdi-package-variant" size="16" class="mr-1" color="primary" />
              {{ g.name }}
              <v-chip size="x-small" class="ml-2" color="warning" variant="tonal">{{ g.items.length }} строки</v-chip>
            </div>
            <v-table density="compact" class="mb-2">
              <thead>
                <tr>
                  <th style="width:36px">№</th>
                  <th style="width:90px">Кол-во</th>
                  <th style="width:110px">Цена ед., ₽</th>
                  <th style="width:120px">Сумма, ₽</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(it, j) in g.items" :key="j">
                  <td class="text-medium-emphasis">{{ j + 1 }}</td>
                  <td>{{ it.quantity ?? '—' }}</td>
                  <td>{{ it.unit_price != null ? Number(it.unit_price).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) : '—' }}</td>
                  <td>{{ it.total_price != null ? Number(it.total_price).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) : '—' }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr style="font-weight:700; background: rgba(0,0,0,0.03)">
                  <td class="text-medium-emphasis">Σ</td>
                  <td>{{ sumQty(g) }}</td>
                  <td>—</td>
                  <td>{{ sumTotal(g) != null ? Number(sumTotal(g)).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) : '—' }}</td>
                </tr>
              </tfoot>
            </v-table>
            <v-alert
              v-if="hasDifferentPrices(g)"
              type="warning"
              density="compact"
              variant="tonal"
              class="mb-2 text-caption"
              icon="mdi-alert-outline"
            >
              Цены строк различаются. При объединении будет выбрана максимальная цена единицы, итог = сумма строк.
            </v-alert>
            <v-radio-group v-model="g._choice" inline density="compact" hide-details>
              <v-radio label="Объединить в одну позицию" value="merge" color="primary" />
              <v-radio label="Оставить раздельно" value="keep" color="grey" />
            </v-radio-group>
          </div>
        </template>

        <!-- mode="tz" — дубли строк ТЗ закупки (backend/app/services/tz_items.py),
             группы приходят с сервера через useTzRows, три варианта решения
             (владелец, 21.09, corrections-21-09.md W3). -->
        <template v-else>
          <div
            v-for="(g, i) in localTzGroups"
            :key="g.key ?? i"
            class="mb-4 pa-3 rounded"
            style="border: 1px solid rgba(0,0,0,0.12)"
          >
            <div class="text-body-2 font-weight-medium mb-2">
              <v-icon icon="mdi-package-variant" size="16" class="mr-1" color="primary" />
              {{ g.name }}
              <v-chip size="x-small" class="ml-2" color="warning" variant="tonal">
                {{ (g.rows?.length || g.item_ids?.length || 0) }} строки
              </v-chip>
            </div>
            <v-table density="compact" class="mb-2" v-if="g.rows?.length">
              <thead>
                <tr>
                  <th style="width:36px">№</th>
                  <th style="width:90px">Кол-во</th>
                  <th style="width:110px">Цена ед., ₽</th>
                  <th style="width:120px">Сумма, ₽</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(it, j) in g.rows" :key="j">
                  <td class="text-medium-emphasis">{{ j + 1 }}</td>
                  <td>{{ it.quantity ?? '—' }}</td>
                  <td>{{ it.unit_price != null ? Number(it.unit_price).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) : '—' }}</td>
                  <td>{{ it.total_price != null ? Number(it.total_price).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) : '—' }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr style="font-weight:700; background: rgba(0,0,0,0.03)">
                  <td class="text-medium-emphasis">Σ</td>
                  <td>{{ g.qty_sum ?? '—' }}</td>
                  <td>—</td>
                  <td>{{ g.total_sum != null ? Number(g.total_sum).toLocaleString('ru-RU', { minimumFractionDigits: 2 }) : '—' }}</td>
                </tr>
              </tfoot>
            </v-table>
            <v-alert
              v-if="g.prices_differ"
              type="warning"
              density="compact"
              variant="tonal"
              class="mb-2 text-caption"
              icon="mdi-alert-outline"
            >
              Цены строк различаются. При объединении цена ед. будет усреднена (сумма / количество).
            </v-alert>
            <v-radio-group v-model="g._choice" inline density="compact" hide-details>
              <v-radio label="Объединить в ТЗ" value="merge" color="primary" />
              <v-radio label="Оставить как есть" value="keep" color="grey" />
              <v-radio label="Ошибка — вернуть на доработку" value="error" color="error" />
            </v-radio-group>
          </div>
        </template>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-btn variant="tonal" @click="onMergeAll">Объединить все</v-btn>
        <v-btn variant="text" color="grey" @click="onKeepAll">{{ mode === 'tz' ? 'Оставить все как есть' : 'Оставить все раздельно' }}</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="elevated" @click="onConfirm">Применить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDisplay } from 'vuetify'

const { mobile } = useDisplay()

interface DupItem {
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  [key: string]: any
}

export interface DupGroup {
  product_id: number
  name: string
  items: DupItem[]
  _choice?: 'merge' | 'keep'
}

export interface ResolvedGroup {
  product_id: number
  choice: 'merge' | 'keep'
  mergedItem: DupItem | null
  originalItems: DupItem[]
}

// mode="tz" — дубли строк ТЗ закупки (Правило №6: группировка/агрегаты
// считаются ТОЛЬКО на бэкенде, backend/app/services/tz_items.py; сюда группы
// приходят уже готовые через composables/purchase/useTzRows.ts).
export interface TzDialogRow {
  quantity: number | null
  unit_price: number | null
  total_price: number | null
  [key: string]: any
}
export interface TzDialogGroup {
  key: string
  name: string
  unit: string
  prices_differ: boolean
  qty_sum: number | null
  total_sum: number | null
  item_ids?: (number | null)[]
  decision: 'merge' | 'keep' | null
  rows: TzDialogRow[]
}
export interface TzConfirmPayload {
  decisions: Record<string, 'merge' | 'keep'>
  errorKeys: string[]
  errorNames: string[]
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  groups?: DupGroup[]
  mode?: 'items' | 'tz'
  tzGroups?: TzDialogGroup[]
}>(), {
  groups: () => [],
  mode: 'items',
  tzGroups: () => [],
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', resolved: ResolvedGroup[]): void
  (e: 'confirm-tz', payload: TzConfirmPayload): void
}>()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// Local copy so we can mutate _choice without modifying props. Два раздельных
// массива (не union на одном) — иначе шаблон и хелперы (sumQty/sumTotal/…,
// которые понимают только DupGroup) требовали бы приведений типов на каждом
// обращении к g.items.
const localGroups = ref<(DupGroup & { _choice: 'merge' | 'keep' })[]>([])
const localTzGroups = ref<(TzDialogGroup & { _choice: 'merge' | 'keep' | 'error' })[]>([])

watch(
  () => props.groups,
  (groups) => {
    localGroups.value = (groups || []).map((g) => ({ ...g, items: [...g.items], _choice: 'merge' }))
  },
  { immediate: true },
)
watch(
  () => props.tzGroups,
  (tzGroups) => {
    localTzGroups.value = (tzGroups || []).map((g) => ({
      ...g,
      _choice: g.decision === 'merge' || g.decision === 'keep' ? g.decision : 'keep',
    }))
  },
  { immediate: true },
)

const groupCount = computed(() => (props.mode === 'tz' ? (props.tzGroups || []).length : (props.groups || []).length))
const groupWord = computed(() => {
  const n = groupCount.value
  if (n === 1) return 'группа'
  if (n < 5) return 'группы'
  return 'групп'
})

function sumQty(g: DupGroup): number | string {
  const allNull = g.items.every((it) => it.quantity == null)
  if (allNull) return '—'
  return g.items.reduce((a, it) => a + Number(it.quantity ?? 0), 0)
}

function sumTotal(g: DupGroup): number | null {
  const vals = g.items.map((it) => it.total_price)
  if (vals.every((v) => v == null)) return null
  return vals.reduce((a, b) => (a ?? 0) + (b ?? 0), 0 as number | null)
}

function maxUnitPrice(g: DupGroup): number | null {
  const vals = g.items.map((it) => it.unit_price).filter((v) => v != null) as number[]
  if (!vals.length) return null
  return Math.max(...vals)
}

function hasDifferentPrices(g: DupGroup): boolean {
  const prices = g.items.map((it) => it.unit_price).filter((v) => v != null)
  if (prices.length < 2) return false
  return new Set(prices).size > 1
}

function buildMergedItem(g: DupGroup): DupItem {
  const first = g.items[0]
  const qty = g.items.reduce((a, it) => a + Number(it.quantity ?? 0), 0)
  const up = maxUnitPrice(g)
  const total = g.items.reduce((a, it) => a + Number(it.total_price ?? 0), 0)
  return {
    ...first,
    // Исправлено (21.09, corrections-21-09.md W3): qty=0 — валидное явное
    // количество, `0 || null` затирало его null; `??` трогает только
    // null/undefined.
    quantity: qty ?? null,
    unit_price: up,
    total_price: total || null,
  }
}

function onMergeAll() {
  if (props.mode === 'tz') localTzGroups.value.forEach((g) => (g._choice = 'merge'))
  else localGroups.value.forEach((g) => (g._choice = 'merge'))
}

function onKeepAll() {
  if (props.mode === 'tz') localTzGroups.value.forEach((g) => (g._choice = 'keep'))
  else localGroups.value.forEach((g) => (g._choice = 'keep'))
}

function onConfirm() {
  if (props.mode === 'tz') {
    onConfirmTz()
    return
  }
  const resolved: ResolvedGroup[] = localGroups.value.map((g) => ({
    product_id: g.product_id,
    choice: g._choice,
    mergedItem: g._choice === 'merge' ? buildMergedItem(g) : null,
    originalItems: g.items,
  }))
  emit('confirm', resolved)
  show.value = false
}

function onConfirmTz() {
  const decisions: Record<string, 'merge' | 'keep'> = {}
  const errorKeys: string[] = []
  const errorNames: string[] = []
  for (const g of localTzGroups.value) {
    if (g._choice === 'error') {
      errorKeys.push(g.key)
      errorNames.push(g.name)
    } else {
      decisions[g.key] = g._choice
    }
  }
  emit('confirm-tz', { decisions, errorKeys, errorNames })
  show.value = false
}
</script>
