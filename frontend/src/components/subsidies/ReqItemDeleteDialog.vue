<template>
  <!-- ── Удаление позиции закупки (из дерева ФЭО) ── -->
  <v-dialog v-model="state.show" max-width="480">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-delete-outline" color="error" class="mr-2" />
        Удалить позицию
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        Удалить позицию «<b>{{ state.name }}</b>» из закупки?
        <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
          Позиция будет удалена из закупки, суммы закупки пересчитаются.
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="error" :loading="state.deleting" @click="doDelete">Удалить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Удаление позиции закупки прямо из дерева ФЭО — вынесен из SubsidiesView.vue
// (волна 5c). Позиции, пришедшие из заявки, сюда не попадают — см.
// WishBlockedDeleteDialog.vue (точечное удаление запрещено, заявка согласована
// целиком) и ctx.confirmReqItemDelete в SubsidiesView.vue (выбирает диалог).
import { reactive } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const state = reactive({
  show: false, deleting: false,
  catId: null as number | null, purchaseId: null as number | null, itemId: null as number | null, name: '',
})

function open(catId: number, purchaseId: number, itemId: number, name: string) {
  state.catId = catId
  state.purchaseId = purchaseId
  state.itemId = itemId
  state.name = name
  state.show = true
}

async function doDelete() {
  if (!state.itemId || !state.purchaseId) return
  state.deleting = true
  try {
    await apiFetch(`/purchases/${state.purchaseId}/items/${state.itemId}`, { method: 'DELETE' })
    state.show = false
    await ctx.refreshReqData(state.catId ?? undefined)
    showSnack('Позиция удалена из закупки')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || 'Не удалось удалить позицию', 'error')
  } finally {
    state.deleting = false
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

