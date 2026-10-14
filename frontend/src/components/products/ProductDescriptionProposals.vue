<!-- ProductDescriptionProposals.vue — список предложений правок каталога,
     видят только сотрудники с products.edit_catalog (Этап В, план
     item-tz-description.md, владелец 14.10.2026, п.3). Открывается из
     кнопки «Предложения правок (N)» на странице каталога (ProductsView.vue).
     Единственный источник данных — GET /api/products/description-proposals,
     решения — accept/reject эндпоинты того же роутера
     (backend/app/routers/product_description.py), второго механизма
     принятия/отклонения не заводим (ПРАВИЛО №6). -->
<template>
  <v-dialog v-model="show" max-width="900" scrollable>
    <v-card>
      <v-card-title class="text-h6 pt-4 px-6">
        Предложения правок каталога
      </v-card-title>
      <v-card-text class="px-6">
        <div v-if="loading" class="text-center py-6 text-medium-emphasis">Загрузка…</div>
        <div v-else-if="!rows.length" class="text-center py-6 text-medium-emphasis">
          Нет предложений, ожидающих решения
        </div>
        <v-card v-for="row in rows" :key="row.id" variant="outlined" class="mb-3">
          <v-card-text>
            <div class="d-flex flex-wrap align-center ga-2 mb-2">
              <span class="font-weight-medium">{{ row.product_name || `Товар #${row.product_id}` }}</span>
              <v-chip size="x-small" variant="tonal">{{ fieldLabel(row.field) }}</v-chip>
              <span class="text-caption text-medium-emphasis">
                {{ row.proposed_by_name || 'Пользователь' }} — {{ formatDate(row.proposed_at) }}
              </span>
            </div>
            <v-row dense>
              <v-col cols="12" sm="6">
                <div class="text-caption text-medium-emphasis">Сейчас в каталоге</div>
                <div class="text-body-2" style="white-space:pre-line">{{ currentValueOf(row) || '—' }}</div>
              </v-col>
              <v-col cols="12" sm="6">
                <div class="text-caption text-medium-emphasis">Предлагается</div>
                <div class="text-body-2" style="white-space:pre-line">{{ row.proposed_value || '—' }}</div>
              </v-col>
            </v-row>
            <v-text-field
              v-model="comments[row.id]"
              label="Комментарий к решению (необязательно)"
              variant="outlined" density="compact" hide-details class="mt-3"
            />
            <div class="d-flex ga-2 mt-3">
              <v-btn
                size="small" color="error" variant="tonal"
                :loading="deciding === row.id"
                @click="decide(row, 'reject')"
              >
                Отклонить
              </v-btn>
              <v-btn
                size="small" color="primary" variant="elevated"
                :loading="deciding === row.id"
                @click="decide(row, 'accept')"
              >
                Принять
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { formatDate } from '@/composables/products/productsTypes'
import type { Product } from '@/composables/products/productsTypes'
import { useToast } from '@/composables/useToast'
import { describeApiError } from '@/utils/apiErrorMessage'

export interface ProductDescriptionProposalRow {
  id: number
  product_id: number
  product_name: string | null
  field: string
  proposed_value: string | null
  current_value_at_proposal: string | null
  wish_item_id: number | null
  purchase_item_id: number | null
  proposed_by: number | null
  proposed_by_name: string | null
  proposed_at: string
  status: string
  decided_by: number | null
  decided_at: string | null
  decision_comment: string | null
}

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  // Список/счётчик в ProductsView.vue обязан обновиться после каждого
  // решения — он считает тот же эндпоинт отдельно (счётчик на кнопке), не
  // пересчитывая на фронте (ПРАВИЛО №6).
  (e: 'changed'): void
}>()

const show = ref(props.modelValue)
watch(() => props.modelValue, (v) => { show.value = v; if (v) load() })
watch(show, (v) => emit('update:modelValue', v))

const toast = useToast()
const rows = ref<ProductDescriptionProposalRow[]>([])
const productsById = ref<Record<number, Product>>({})
const loading = ref(false)
const deciding = ref<number | null>(null)
const comments = ref<Record<number, string>>({})

const FIELD_LABELS: Record<string, string> = {
  description: 'Точное описание',
  description_44fz: 'Описание для 44-ФЗ',
}
function fieldLabel(f: string): string {
  return FIELD_LABELS[f] || f
}

function currentValueOf(row: ProductDescriptionProposalRow): string | null | undefined {
  const product = productsById.value[row.product_id]
  if (!product) return row.current_value_at_proposal
  return (product as any)[row.field]
}

async function load() {
  loading.value = true
  try {
    rows.value = await apiFetch<ProductDescriptionProposalRow[]>('/products/description-proposals?status=pending')
    const ids = [...new Set(rows.value.map(r => r.product_id))]
    if (ids.length) {
      const products = await apiFetch<Product[]>(`/products/?ids=${ids.join(',')}`)
      productsById.value = Object.fromEntries(products.map(p => [p.id, p]))
    } else {
      productsById.value = {}
    }
  } catch (e: any) {
    toast.error(describeApiError(e, { fallback: 'Не удалось загрузить предложения' }))
  } finally {
    loading.value = false
  }
}

async function decide(row: ProductDescriptionProposalRow, action: 'accept' | 'reject') {
  deciding.value = row.id
  try {
    const comment = comments.value[row.id]?.trim() || undefined
    if (action === 'accept') {
      const res = await apiFetch<{ changed_since_proposal: boolean }>(
        `/products/description-proposals/${row.id}/accept`,
        { method: 'POST', body: { comment } },
      )
      toast.success(
        res.changed_since_proposal
          ? 'Предложение принято. Внимание: описание в каталоге изменилось после подачи предложения.'
          : 'Предложение принято, каталог обновлён',
      )
    } else {
      await apiFetch(`/products/description-proposals/${row.id}/reject`, { method: 'POST', body: { comment } })
      toast.success('Предложение отклонено')
    }
    rows.value = rows.value.filter(r => r.id !== row.id)
    emit('changed')
  } catch (e: any) {
    toast.error(describeApiError(e, { fallback: 'Не удалось сохранить решение' }))
  } finally {
    deciding.value = null
  }
}

defineExpose({ reload: load })
</script>
