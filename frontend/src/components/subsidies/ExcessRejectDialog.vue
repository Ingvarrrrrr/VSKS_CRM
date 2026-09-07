<template>
  <!-- ── Отклонить превышение плана ФЭО — обязательный комментарий (задача владельца 2026-08-05) ── -->
  <v-dialog v-model="state.show" max-width="440">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-close-circle-outline" color="error" class="mr-2" />
        Отклонить превышение плана
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="state.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="mb-2">«{{ state.node?.name }}»</div>
        <v-textarea v-model="state.comment" label="Причина отклонения" density="comfortable"
          variant="outlined" rows="3" autofocus hide-details="auto" />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="error" :loading="ctx.excessDecideLoading.value === state.node?.id" @click="submit">Отклонить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Отклонение согласования превышения плана ФЭО (задача владельца 2026-08-05) —
// вынесен из SubsidiesView.vue (волна 5c). Открывается через
// ctx.openExcessRejectDialog(node) (трамполин вызывает open() этого компонента
// через ref, см. её докстринг); само решение (decidePlanExcess) — в
// useFeoTreeExcess.ts, единственный источник (Правило №6).
import { reactive } from 'vue'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { FeoNode } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const state = reactive<{ show: boolean; node: FeoNode | null; comment: string }>({
  show: false, node: null, comment: '',
})

function open(node: FeoNode) {
  state.show = true
  state.node = node
  state.comment = ''
}

async function submit() {
  const node = state.node
  if (!node) return
  if (!state.comment.trim()) {
    showSnack('Укажите причину отклонения', 'error')
    return
  }
  await ctx.decidePlanExcess(node, 'rejected', state.comment.trim())
  state.show = false
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

