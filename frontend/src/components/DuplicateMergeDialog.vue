<template>
  <v-dialog v-model="show" max-width="900" scrollable persistent>
    <v-card>
      <v-card-title class="text-subtitle-1 font-weight-bold d-flex align-center gap-2 px-4 pt-4">
        <v-icon icon="mdi-content-duplicate" color="warning" />
        Обнаружены дублирующиеся позиции
      </v-card-title>
      <v-card-subtitle class="px-4 pb-2 text-medium-emphasis">
        Найдено {{ groups.length }} {{ groupWord }} с несколькими строками с одним товаром. Выберите, что сделать с каждой.
      </v-card-subtitle>
      <v-divider />
      <v-card-text class="pa-4">
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
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-3">
        <v-btn variant="tonal" @click="onMergeAll">Объединить все</v-btn>
        <v-btn variant="text" color="grey" @click="onKeepAll">Оставить все раздельно</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="elevated" @click="onConfirm">Применить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

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

const props = defineProps<{
  modelValue: boolean
  groups: DupGroup[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', resolved: ResolvedGroup[]): void
}>()

const show = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// Local copy so we can mutate _choice without modifying props
const localGroups = ref<(DupGroup & { _choice: 'merge' | 'keep' })[]>([])

watch(
  () => props.groups,
  (groups) => {
    localGroups.value = groups.map((g) => ({ ...g, items: [...g.items], _choice: 'merge' }))
  },
  { immediate: true },
)

const groupWord = computed(() => {
  const n = props.groups.length
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
    quantity: qty || null,
    unit_price: up,
    total_price: total || null,
  }
}

function onMergeAll() {
  localGroups.value.forEach((g) => (g._choice = 'merge'))
}

function onKeepAll() {
  localGroups.value.forEach((g) => (g._choice = 'keep'))
}

function onConfirm() {
  const resolved: ResolvedGroup[] = localGroups.value.map((g) => ({
    product_id: g.product_id,
    choice: g._choice,
    mergedItem: g._choice === 'merge' ? buildMergedItem(g) : null,
    originalItems: g.items,
  }))
  emit('confirm', resolved)
  show.value = false
}
</script>
