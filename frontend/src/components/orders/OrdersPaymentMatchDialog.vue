<template>
  <!-- Разнести платежи (Этап 7а) — прогон match-payments по субсидии -->
  <v-dialog v-model="state.show" max-width="720" scrollable :fullscreen="mobile" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon start color="indigo">mdi-bank-transfer</v-icon>
        Разнести платежи
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="closeDialog" />
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-select
          v-model="state.subsidyId"
          :items="subsidies"
          item-title="name"
          item-value="id"
          label="Субсидия"
          variant="outlined"
          density="compact"
          :disabled="!!state.report"
          hide-details
          class="mb-3"
        />

        <div v-if="!state.report" class="text-caption text-medium-emphasis mb-2">
          Найдёт группы закупок субсидии (по договору + реестровому номеру), подберёт
          платежи из реестра по ИНН, сумме и коду расходов, и покажет предпросмотр —
          ничего не изменится, пока вы не нажмёте «Применить».
        </div>

        <div v-if="state.loading" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="indigo" />
        </div>

        <template v-else-if="state.report">
          <div class="d-flex flex-wrap gap-2 mb-3">
            <v-chip color="grey" variant="tonal" size="small">Групп всего: {{ state.report.groups_total }}</v-chip>
            <v-chip color="success" variant="tonal" size="small">
              {{ state.applied ? 'Разнесено' : 'Будет разнесено' }}: {{ state.report.attached.length }}
            </v-chip>
            <v-chip color="warning" variant="tonal" size="small">Неоднозначно: {{ state.report.ambiguous.length }}</v-chip>
            <v-chip color="grey" variant="tonal" size="small">Не найдено: {{ state.report.not_found.length }}</v-chip>
            <v-chip v-if="state.report.suspicious.length" color="error" variant="tonal" size="small">
              Подозрительные дубли: {{ state.report.suspicious.length }}
            </v-chip>
          </div>

          <div v-if="state.report.attached.length" class="mb-3">
            <div class="text-subtitle-2 font-weight-bold mb-1">
              {{ state.applied ? 'Разнесено' : 'Будет разнесено' }}
            </div>
            <div v-for="g in state.report.attached" :key="g.group_key" class="text-body-2 mb-1">
              Реестр № {{ g.registry_number || '—' }}:
              <span v-for="(it, i) in g.items" :key="i">
                {{ it.kind === 'goods' ? 'товары' : 'услуги' }} {{ formatMoney(it.amount) }}{{ i < g.items.length - 1 ? ', ' : '' }}
              </span>
            </div>
          </div>

          <div v-if="state.report.ambiguous.length" class="mb-3">
            <div class="text-subtitle-2 font-weight-bold mb-1 text-warning">Неоднозначно — требует ручного разбора</div>
            <div v-for="g in state.report.ambiguous" :key="g.group_key" class="text-body-2 mb-1">
              Реестр № {{ g.registry_number || '—' }}:
              <span v-for="(it, i) in g.items" :key="i">
                {{ it.kind === 'goods' ? 'товары' : 'услуги' }} — {{ it.reason }}{{ i < g.items.length - 1 ? '; ' : '' }}
              </span>
            </div>
          </div>

          <div v-if="state.report.not_found.length" class="mb-3">
            <div class="text-subtitle-2 font-weight-bold mb-1">Не найдено ни одного кандидата</div>
            <div class="text-body-2">
              {{ state.report.not_found.map((g: any) => `№ ${g.registry_number || '—'}`).join(', ') }}
            </div>
          </div>

          <v-alert v-if="state.report.suspicious.length" type="warning" variant="tonal" density="compact" class="mb-2">
            {{ state.report.suspicious.length }} групп(ы) закупок похожи на дубликаты
            (одинаковая сумма, пустой предмет, без договора/субсидии) — они пропущены и требуют
            ручного разбора реестровых номеров, прежде чем участвовать в разнесении.
          </v-alert>

          <v-alert v-if="state.applied" type="success" variant="tonal" density="compact">
            Готово. Обновите реестр закупок, чтобы увидеть новые платежи.
          </v-alert>
        </template>

        <v-alert v-if="state.error" type="error" variant="tonal" density="compact" class="mt-2">
          {{ state.error }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer />
        <template v-if="!state.report">
          <v-btn variant="text" @click="closeDialog">Отмена</v-btn>
          <v-btn color="indigo" variant="flat" :disabled="!state.subsidyId" :loading="state.loading" @click="runPreview">
            Предпросмотр
          </v-btn>
        </template>
        <template v-else-if="!state.applied">
          <v-btn variant="text" @click="state.report = null">Назад</v-btn>
          <v-btn
            color="indigo" variant="flat" :loading="state.loading"
            :disabled="!state.report.attached.length"
            @click="applyMatch"
          >
            Применить ({{ state.report.attached.length }})
          </v-btn>
        </template>
        <template v-else>
          <v-btn color="primary" variant="flat" @click="closeDialog">Готово</v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { formatMoney } from '@/utils/formatMoney'
import type { ToastType } from '@/composables/useToast'
import type { PaymentMatchReport, Subsidy } from '@/composables/orders/ordersTypes'

const props = defineProps<{
  subsidies: Subsidy[]
  showSnack: (text: string, color?: ToastType) => void
  onApplied: () => void
}>()

const { mobile } = useDisplay()

const state = reactive({
  show: false,
  subsidyId: null as number | null,
  loading: false,
  applied: false,
  report: null as PaymentMatchReport | null,
  error: '',
})

function open(initialSubsidyId: number | null) {
  state.show = true
  state.subsidyId = initialSubsidyId ?? null
  state.loading = false
  state.applied = false
  state.report = null
  state.error = ''
}

function closeDialog() {
  state.show = false
  if (state.applied) {
    props.onApplied()
  }
}

async function runPreview() {
  if (!state.subsidyId) return
  state.loading = true
  state.error = ''
  try {
    state.report = await apiFetch<PaymentMatchReport>(
      `/purchases/match-payments?subsidy_id=${state.subsidyId}&dry_run=true`,
      { method: 'POST' }
    )
  } catch (e: any) {
    state.error = e?.payload?.message || e?.detail || e?.message || 'Ошибка предпросмотра'
  } finally {
    state.loading = false
  }
}

async function applyMatch() {
  if (!state.subsidyId) return
  state.loading = true
  state.error = ''
  try {
    state.report = await apiFetch<PaymentMatchReport>(
      `/purchases/match-payments?subsidy_id=${state.subsidyId}&dry_run=false`,
      { method: 'POST' }
    )
    state.applied = true
    props.showSnack(`Разнесено платежей: ${state.report.attached.length}`, 'success')
  } catch (e: any) {
    state.error = e?.payload?.message || e?.detail || e?.message || 'Ошибка применения'
  } finally {
    state.loading = false
  }
}

defineExpose({ open })
</script>
