<template>
  <!-- ── Позиция из заявки: точечное удаление запрещено — объясняем и даём легальный путь ── -->
  <v-dialog v-model="state.show" max-width="520">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-information-outline" color="primary" class="mr-2" />
        Позиция создана заявкой №{{ state.wishId }}
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        Позиция «<b>{{ state.name }}</b>» ({{ state.quantity }} {{ state.unit || 'шт' }}, {{ formatCurrency(state.sum) }} ₽)
        пришла из заявки №{{ state.wishId }}.
        <v-alert type="warning" variant="tonal" density="compact" class="mt-3">
          Позиции согласованной заявки нельзя убирать из плана по одной: заявка меняется целиком и уходит на повторное согласование.
        </v-alert>
        <div class="mt-3">
          Чтобы убрать её из плана-графика — откройте заявку и отредактируйте состав. При сохранении она вернётся на согласование и уйдёт из плана автоматически.
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="primary" @click="openWish">Открыть заявку</v-btn>
        <v-btn v-if="ctx.isSaas.value" color="warning" :loading="state.reverting" @click="revertToDraft">Вернуть заявку в черновик</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Позиция «из заявки»: точечно удалить её из плана нельзя — заявка уже
// согласована, и убрать одну строку в обход цепочки согласующих значит сломать
// инвариант «изменил заявку → она уходит на повторное согласование». Вынесен
// из SubsidiesView.vue (волна 5c) — открывается через ctx.confirmReqItemDelete,
// который решает, показать этот диалог или ReqItemDeleteDialog.vue.
import { reactive } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const state = reactive({
  show: false, reverting: false,
  wishId: null as number | null, catId: null as number | null,
  name: '', quantity: null as number | null, unit: '' as string | null, sum: 0,
})

function open(wishId: number, catId: number, name: string, quantity: number | null, unit: string | null, sum: number) {
  state.wishId = wishId
  state.catId = catId
  state.name = name
  state.quantity = quantity
  state.unit = unit
  state.sum = sum
  state.show = true
}

function openWish() {
  state.show = false
  ctx.router.push({ path: '/wishes', query: { open: String(state.wishId) } })
}

// Только для SaaS-ролей: принудительно вернуть заявку в черновик — эндпоинт сам убирает
// всю заявку (не одну позицию) из плана-графика.
async function revertToDraft() {
  if (!state.wishId) return
  state.reverting = true
  try {
    const res = await apiFetch<{ convert_warning?: string | null }>(`/wishes/${state.wishId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status: 'draft' }),
    })
    state.show = false
    if (res?.convert_warning) {
      showSnack(`Заявка №${state.wishId} возвращена в черновик. ${res.convert_warning}`, 'warning')
    } else {
      showSnack(`Заявка №${state.wishId} возвращена в черновик и убрана из плана`)
    }
    await ctx.refreshReqData(state.catId ?? undefined)
    await ctx.loadResiduals()
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось вернуть заявку в черновик', 'error')
  } finally {
    state.reverting = false
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

