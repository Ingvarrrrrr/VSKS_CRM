<template>
  <v-dialog v-model="dialog" max-width="800" scrollable>
    <v-card>
      <v-card-title class="d-flex align-center pa-4" style="background: #1e3a5f; color: white; flex-shrink: 0">
        <v-icon icon="mdi-history" class="mr-2" />
        <span style="flex: 1; min-width: 0">История бюджета: {{ currentSubsidyName }}</span>
        <v-btn icon="mdi-close" variant="text" color="white" size="small" @click="dialog = false" />
      </v-card-title>

      <v-card-text class="pa-4" style="overflow-y: auto">
        <!-- Loading state -->
        <div v-if="loading" class="d-flex justify-center align-center py-12">
          <v-progress-circular indeterminate color="primary" size="48" />
        </div>

        <!-- Empty state -->
        <div
          v-else-if="items.length === 0"
          class="d-flex flex-column align-center justify-center py-12 text-medium-emphasis"
        >
          <v-icon icon="mdi-clock-outline" size="48" class="mb-3" />
          <div>Изменений ещё не было</div>
        </div>

        <!-- Timeline -->
        <v-timeline v-else density="compact" side="end">
          <v-timeline-item
            v-for="item in items"
            :key="item.id"
            :dot-color="item.entity_type === 'subsidy' ? 'orange' : 'blue'"
            size="small"
          >
            <div class="text-caption text-medium-emphasis mb-1">
              {{ formatDate(item.changed_at) }} — {{ item.changed_by_name || 'Система' }}
            </div>
            <div class="text-body-2">
              {{ entityLabel(item) }}: {{ fmt(item.old_value) }} → {{ fmt(item.new_value) }}
            </div>
            <div v-if="item.reason" class="text-caption font-italic text-medium-emphasis mt-1">
              {{ item.reason }}
            </div>
          </v-timeline-item>
        </v-timeline>

        <!-- Load-more button -->
        <div v-if="total > items.length" class="d-flex justify-center mt-4">
          <v-btn
            variant="tonal"
            color="primary"
            :loading="loadingMore"
            prepend-icon="mdi-chevron-down"
            @click="loadHistory(false)"
          >
            Загрузить ещё
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetch } from '@/api'

interface HistoryItem {
  id: number
  entity_type: string
  purchase_id: number | null
  old_value: number | null
  new_value: number | null
  changed_by_name: string | null
  reason: string | null
  changed_at: string | null
}

const dialog = ref(false)
const currentSubsidyId = ref<number | null>(null)
const currentSubsidyName = ref('')
const items = ref<HistoryItem[]>([])
const total = ref(0)
const loading = ref(false)
const loadingMore = ref(false)
const PAGE_SIZE = 50

async function loadHistory(reset = true) {
  if (!currentSubsidyId.value) return
  if (reset) {
    loading.value = true
    items.value = []
  } else {
    loadingMore.value = true
  }
  try {
    const offset = reset ? 0 : items.value.length
    const data = await apiFetch<{ total: number; items: HistoryItem[] }>(
      `/subsidies/${currentSubsidyId.value}/history?offset=${offset}&limit=${PAGE_SIZE}`
    )
    total.value = data.total
    if (reset) {
      items.value = data.items
    } else {
      items.value.push(...data.items)
    }
  } catch (e) {
    console.error('history load error', e)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

function open(subsidyId: number, subsidyName: string) {
  currentSubsidyId.value = subsidyId
  currentSubsidyName.value = subsidyName
  dialog.value = true
  loadHistory(true)
}

function entityLabel(item: HistoryItem): string {
  return item.entity_type === 'subsidy' ? 'Лимит субсидии' : 'Сумма закупки'
}

function fmt(val: number | null): string {
  if (val === null || val === undefined) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 0,
  }).format(val)
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

defineExpose({ open })
</script>
