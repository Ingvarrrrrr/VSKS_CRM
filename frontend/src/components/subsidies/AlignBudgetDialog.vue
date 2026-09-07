<template>
  <!-- ── «Приравнять ФЭО к плану» — подтверждение с текущими числами (замечание владельца п.3, 2026-08-12) ── -->
  <v-dialog v-model="state.show" max-width="440">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-equal" color="primary" class="mr-2" />
        Приравнять ФЭО к плану?
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="state.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <div class="mb-2">«{{ state.node?.name }}»</div>
        <div>ФЭО категории станет {{ formatCurrency(state.newBudget) }} вместо {{ formatCurrency(state.oldBudget) }}</div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="primary" :loading="loading === state.node?.id" @click="confirm">Приравнять</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Замечание владельца п.3 (2026-08-12): «Приравнять ФЭО к плану» — POST
// /feo-categories/{id}/align-budget-to-plan. Вынесен из SubsidiesView.vue (волна
// 5c) — открывается через ctx.openAlignBudgetConfirm(node) (трамполин в
// SubsidiesView.vue вызывает open() этого компонента через ref, см. её докстринг).
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import type { FeoNode } from '@/composables/subsidies/types'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const loading = ref<number | null>(null)
const state = reactive<{ show: boolean; node: FeoNode | null; newBudget: number; oldBudget: number }>({
  show: false, node: null, newBudget: 0, oldBudget: 0,
})

function open(node: FeoNode) {
  const t = ctx.planTreeByCat.value[node.id]
  const newBudget = Number(t?.plan || 0) + Number(t?.over || 0)
  state.show = true
  state.node = node
  state.newBudget = newBudget
  state.oldBudget = Number(node.budget || 0)
}

async function confirm() {
  const node = state.node
  if (!node) return
  loading.value = node.id
  try {
    await apiFetch(`/feo-categories/${node.id}/align-budget-to-plan`, { method: 'POST' })
    state.show = false
    showSnack('Финансирование по ФЭО приравнено к плану', 'success')
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
  } catch (e: any) {
    // Ошибку показываем распакованной (в т.ч. отказ по общему потолку субсидии,
    // код PLAN_OVER_SUBSIDY_CEILING) — showSnack по умолчанию без автозакрытия.
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Не удалось приравнять ФЭО к плану', 'error')
  } finally {
    loading.value = null
  }
}

defineExpose({ open })
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>

