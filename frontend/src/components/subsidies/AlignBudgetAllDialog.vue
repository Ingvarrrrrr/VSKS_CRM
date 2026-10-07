<template>
  <!-- ── «Приравнять ФЭО к плану по всем статьям» — подтверждение прямо в
       странице (владелец 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-
       cards/PLAN.md шаг 3-5, решение №4). Отдельный файл (Правило №5) — новая
       логика («одним действием на всю субсидию»), не дописывание в
       AlignBudgetDialog.vue (та — одна категория, своя кнопка/эндпоинт). ── -->
  <v-dialog v-model="state.show" max-width="460">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-equal-box" color="primary" class="mr-2" />
        Приравнять ФЭО к плану по всем статьям?
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="state.show = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <template v-if="state.count > 0">
          <div>ФЭО станет равным плану у {{ state.count }} {{ pluralStatey(state.count) }} на сумму {{ formatCurrency(state.total) }}.</div>
          <div class="text-caption text-medium-emphasis mt-2">Остальные статьи субсидии уже равны плану — их финансирование не изменится.</div>
        </template>
        <template v-else>
          <div>У всех статей субсидии ФЭО уже равно плану — менять нечего.</div>
        </template>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="state.show = false">Отмена</v-btn>
        <v-btn color="primary" :disabled="state.count === 0" :loading="loading" @click="confirm">Приравнять</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// POST /api/subsidies/{id}/feo/align-budget-to-plan-all (backend/app/routers/
// feo_tree_ops.py) — ФЭО := план (plan+over, то же целевое значение, что у
// одиночного «Приравнять», см. AlignBudgetDialog.vue) у КАЖДОЙ статьи
// субсидии разом. N/X в подтверждении считаются из УЖЕ загруженного дерева
// (ctx.feoCategories/ctx.planTreeByCat) — тот же источник, что одиночный
// диалог читает для одной категории, здесь просто сумма по всем (Правило №6 —
// не второй расчёт, та же формула budget:=plan+over на каждой категории).
import { reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'

const ctx = useSubsidyDetailCtx()

const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

function pluralStatey(n: number): string {
  const n10 = n % 10
  const n100 = n % 100
  if (n100 >= 11 && n100 <= 14) return 'статей'
  if (n10 === 1) return 'статье'
  if (n10 >= 2 && n10 <= 4) return 'статьях'
  return 'статей'
}

const loading = ref(false)
const state = reactive<{ show: boolean; subsidyId: number | null; count: number; total: number }>({
  show: false, subsidyId: null, count: 0, total: 0,
})

function open(subsidyId: number) {
  let count = 0
  let total = 0
  for (const cat of ctx.feoCategories.value) {
    const t = ctx.planTreeByCat.value[cat.id]
    const newBudget = Number(t?.plan || 0) + Number(t?.over || 0)
    const oldBudget = Number(cat.budget || 0)
    if (Math.abs(newBudget - oldBudget) > 0.005) {
      count += 1
      total += newBudget
    }
  }
  state.subsidyId = subsidyId
  state.count = count
  state.total = total
  state.show = true
}

async function confirm() {
  const subsidyId = state.subsidyId
  if (!subsidyId) return
  loading.value = true
  try {
    const res = await apiFetch<{ subsidy_id: number; count: number; total: number }>(
      `/subsidies/${subsidyId}/feo/align-budget-to-plan-all`,
      { method: 'POST' },
    )
    state.show = false
    showSnack(`ФЭО приравнено к плану у ${res.count} ${pluralStatey(res.count)} на сумму ${formatCurrency(res.total)}`, 'success')
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
    // Карточка субсидии («Бюджет (ФЭО)»/«Свободно») живёт на calculated_budget
    // строки субсидии, не на дереве — loadFeo выше её не трогает. Без этого
    // вызова карточка после «Приравнять» оставалась бы «ФЭО не введено» до
    // следующей полной перезагрузки списка (ПРАВИЛО №6, тот же механизм, что
    // SubsidyEditDialog.vue — Object.assign по ссылке, без моргания сетки).
    await ctx.silentRefreshSubsidies()
  } catch (e: any) {
    // Ошибку показываем распакованной, текстом сервера — без общего
    // generic-сообщения (ПРАВИЛО: объяснять причину блокировки).
    showSnack(e?.payload?.message || e?.payload?.detail || e?.detail || e?.message || 'Не удалось приравнять ФЭО к плану по всем статьям', 'error')
  } finally {
    loading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
/* .dialog-card/.dialog-title — тот же паттерн, что AlignBudgetDialog.vue (её
   докстринг: scoped CSS другого файла не достаёт, повторяем здесь). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
