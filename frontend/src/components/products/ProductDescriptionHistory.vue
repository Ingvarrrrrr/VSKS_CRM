<!-- ProductDescriptionHistory.vue — история правок описания товара в каталоге
     (Этап В, план item-tz-description.md, владелец 14.10.2026, п.2). Один
     источник данных — GET /api/products/{id}/description-history
     (backend/app/routers/product_description.py), «Вернуть прежнее» зовёт
     тот же единственный revert-эндпоинт. Встраивается в ProductFormDialog.vue
     только когда товар уже существует (при создании истории ещё нет). -->
<template>
  <v-card variant="outlined" class="mt-4">
    <v-card-title class="text-subtitle-2 d-flex align-center" style="cursor:pointer" @click="collapsed = !collapsed">
      <v-icon icon="mdi-history" size="18" class="mr-2" />
      История описаний
      <v-chip v-if="rows.length" size="x-small" class="ml-2" variant="tonal">{{ rows.length }}</v-chip>
      <v-spacer />
      <v-icon :icon="collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'" size="18" color="grey" />
    </v-card-title>
    <v-card-text v-show="!collapsed" class="pt-0">
      <div v-if="loading" class="text-center py-3 text-medium-emphasis">Загрузка…</div>
      <div v-else-if="!rows.length" class="text-caption text-medium-emphasis">История пуста</div>
      <div v-else>
        <div v-for="row in rows" :key="row.id" class="mb-3 pb-3" style="border-bottom:1px solid rgba(0,0,0,0.08)">
          <div class="text-caption text-medium-emphasis mb-1">
            {{ row.user_name || 'Система' }} — {{ formatDate(row.changed_at) }} — {{ fieldLabel(row.field) }}
            <span v-if="row.source === 'proposal'">(по предложению)</span>
            <span v-else-if="row.source === 'revert'">(возврат)</span>
            <span v-else-if="row.source === 'fill_empty'">(заполнено пустое поле без права «Редактировать каталог»)</span>
          </div>
          <v-row dense>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis">Было</div>
              <div class="text-body-2" style="white-space:pre-line">{{ row.old_value || '—' }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="text-caption text-medium-emphasis">Стало</div>
              <div class="text-body-2" style="white-space:pre-line">{{ row.new_value || '—' }}</div>
            </v-col>
          </v-row>
          <v-btn
            v-if="canEditCatalog"
            size="x-small" variant="text" color="primary" density="compact"
            prepend-icon="mdi-restore" class="mt-1"
            :loading="reverting === row.id"
            @click="revert(row)"
          >
            Вернуть прежнее
          </v-btn>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { formatDate } from '@/composables/products/productsTypes'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

export interface ProductDescriptionHistoryRow {
  id: number
  product_id: number
  field: string
  old_value: string | null
  new_value: string | null
  user_id: number | null
  user_name: string | null
  changed_at: string
  source: string
  proposal_id: number | null
}

const props = defineProps<{
  productId: number | null
  canEditCatalog: boolean
}>()

const emit = defineEmits<{
  // Возврат применился к товару в каталоге — родитель (ProductFormDialog)
  // обязан перечитать карточку с сервера, иначе форма продолжит показывать
  // старое значение поля (ПРАВИЛО №6 — одно место истины, сервер).
  (e: 'reverted'): void
}>()

const collapsed = ref(true)
const rows = ref<ProductDescriptionHistoryRow[]>([])
const loading = ref(false)
const reverting = ref<number | null>(null)
const toast = useToast()

const FIELD_LABELS: Record<string, string> = {
  description: 'Точное описание',
  description_44fz: 'Описание для 44-ФЗ',
}
function fieldLabel(f: string): string {
  return FIELD_LABELS[f] || f
}

async function load() {
  if (!props.productId) { rows.value = []; return }
  loading.value = true
  try {
    rows.value = await apiFetch<ProductDescriptionHistoryRow[]>(`/products/${props.productId}/description-history`)
  } catch (e: any) {
    toast.error(describeApiError(e, { fallback: 'Не удалось загрузить историю описаний' }))
  } finally {
    loading.value = false
  }
}

watch(() => props.productId, load, { immediate: true })

async function revert(row: ProductDescriptionHistoryRow) {
  if (!props.productId) return
  reverting.value = row.id
  try {
    await apiFetch(`/products/${props.productId}/description-history/${row.id}/revert`, { method: 'POST' })
    toast.success('Прежнее значение возвращено')
    await load()
    emit('reverted')
  } catch (e: any) {
    toast.error(describeApiError(e, { fallback: 'Не удалось вернуть прежнее значение' }))
  } finally {
    reverting.value = null
  }
}

defineExpose({ reload: load })
</script>
