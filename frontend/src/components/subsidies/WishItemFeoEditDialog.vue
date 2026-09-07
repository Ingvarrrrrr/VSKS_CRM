<template>
  <!-- ── Смена категории ФЭО у wish-позиции ── -->
  <v-dialog v-model="state.show" max-width="520">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-swap-horizontal" color="primary" class="mr-2" />
        Сменить категорию ФЭО
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="state.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="text-body-2 text-medium-emphasis mb-3">
          Позиция: <b>{{ state.itemName }}</b>
        </div>
        <v-select
          v-model="state.selectedCatId"
          :items="leafFeoCategories"
          item-title="name"
          item-value="id"
          label="Категория ФЭО"
          density="comfortable"
          variant="outlined"
          clearable
          hide-details="auto"
          class="mb-3"
        />
        <div class="mt-1">
          <v-btn
            size="small"
            variant="tonal"
            color="orange"
            prepend-icon="mdi-package-variant"
            :loading="state.unallocatedLoading"
            @click="pickUnallocated"
          >
            ❓ Не определена
          </v-btn>
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="primary" :loading="state.saving" :disabled="state.selectedCatId == null" @click="save">Сохранить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Смена ФЭО-категории у wish-позиции (кнопка mdi-swap-horizontal в строках «из
// заявок») — вынесен из SubsidiesView.vue (волна 5c). Открывается через
// ctx.openWishItemFeoEdit(node, item).
import { computed, reactive } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { FeoNode, FeoReqItem } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const state = reactive({
  show: false,
  saving: false,
  unallocatedLoading: false,
  purchaseId: null as number | null,
  itemId: null as number | null,
  itemName: '',
  catId: null as number | null,   // текущий catId для refreshReqData
  selectedCatId: null as number | null,
})

// Только листовые категории текущей субсидии
const leafFeoCategories = computed(() =>
  ctx.feoCategories.value.filter(c => !ctx.feoCategories.value.some(x => x.parent_id === c.id))
)

function open(node: FeoNode, item: FeoReqItem) {
  state.catId = node.id
  state.purchaseId = item.purchase_id
  state.itemId = item.id
  state.itemName = item.item_name
  state.selectedCatId = null
  state.show = true
}

async function save() {
  if (!state.itemId || !state.purchaseId || state.selectedCatId == null) return
  state.saving = true
  try {
    const _feoRes = await apiFetch<any>(`/purchases/${state.purchaseId}/items/${state.itemId}`, {
      method: 'PATCH',
      body: JSON.stringify({ feo_category_id: state.selectedCatId }),
    })
    state.show = false
    await ctx.refreshReqData(state.catId ?? undefined)
    // Владелец (2026-09-03): «перекос ветки — предупреждение, не блокировка».
    if (_feoRes?.excess_warnings?.length) {
      showSnack(_feoRes.excess_warnings.map((w: any) => w.message).join(' '), 'warning')
    } else {
      showSnack('Категория ФЭО обновлена')
    }
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось сменить категорию ФЭО', 'error')
  } finally {
    state.saving = false
  }
}

async function pickUnallocated() {
  if (!ctx.selectedId.value) return
  state.unallocatedLoading = true
  try {
    const cat = await apiFetch<{ id: number; name: string }>('/feo-categories/unallocated', {
      method: 'POST',
      body: JSON.stringify({ subsidy_id: ctx.selectedId.value }),
    })
    if (!ctx.feoCategories.value.find(c => c.id === cat.id)) {
      ctx.feoCategories.value = [...ctx.feoCategories.value, {
        id: cat.id, name: cat.name, parent_id: null, level: 0,
        subsidy_id: ctx.selectedId.value!, code: null, appendix: null,
        is_active: true, budget: null, planned_quantity: null, planned_amount: null, unit: null,
        feo_quantity: null, feo_unit: null, description: null, feo_amount: null,
      }]
    }
    state.selectedCatId = cat.id
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Ошибка получения «Не определена»', 'error')
  } finally {
    state.unallocatedLoading = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>

