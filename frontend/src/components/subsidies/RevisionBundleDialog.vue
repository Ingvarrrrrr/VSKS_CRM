<template>
  <v-dialog v-model="open" max-width="560">
    <v-card>
      <v-card-title class="text-subtitle-1">Откуда деньги на увеличение суммы</v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-3">
          Увеличивая сумму, укажите, за счёт чего: другой строки корректировки, где
          сумма снижена ({{ formatCurrency(opAmountDelta) }}), или свободных денег субсидии.
          Связанные строки получают общий номер связки.
        </div>

        <v-radio-group v-model="choice" density="comfortable" hide-details>
          <v-radio value="free" label="За счёт свободных денег субсидии" />
          <v-radio value="existing" label="Привязать к существующей связке" :disabled="!bundles.length" />
          <v-radio value="source" label="Выбрать строку(и)-источник снижения" :disabled="!availableSources.length" />
        </v-radio-group>

        <v-select
          v-if="choice === 'existing'"
          v-model="selectedBundleNo"
          :items="bundles.map(b => ({ title: `Связка ${b.bundle_no} (баланс ${formatCurrency(b.balance)})`, value: b.bundle_no }))"
          label="Связка" density="compact" class="mt-2" hide-details
        />

        <v-list v-if="choice === 'source'" density="compact" class="mt-2 rev-bundle-list">
          <v-list-item v-for="s in availableSources" :key="s.id" @click="toggleSource(s.id)">
            <template #prepend>
              <v-checkbox-btn :model-value="selectedSourceIds.includes(s.id)" density="compact" />
            </template>
            <v-list-item-title>{{ s.path }}</v-list-item-title>
            <v-list-item-subtitle>{{ formatCurrency(s.before) }} → {{ formatCurrency(s.after) }} (снижение {{ formatCurrency(s.before - s.after) }})</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn color="primary" variant="flat" :disabled="!canConfirm" @click="confirm">Применить</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Диалог связки «откуда деньги» — волна 3B, требование владельца п.4. Связка —
// общий bundle_no у строк корректировки (одна строка со снятием, ссылку на
// которую может переиспользовать несколько увеличений). Пишет ЧЕРЕЗ
// useSubsidyRevision().setBundle — не заводит свой запрос (Правило №6).
import { computed, ref, watch } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'
import type { RevisionOp } from '@/composables/subsidies/useSubsidyRevision'

const props = defineProps<{
  modelValue: boolean
  op: RevisionOp | null
  ops: RevisionOp[]
  bundles: Array<{ bundle_no: number; added: number; removed: number; balance: number }>
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  // null — «свободные деньги» (создаётся новая связка только на эту строку);
  // число — присоединиться к СУЩЕСТВУЮЩЕЙ связке с этим номером; строка
  // "__sources__:1,2" — новая связка из этой строки + выбранных source-строк
  // (вызывающий компонент сам зовёт useSubsidyRevision().createBundle).
  (e: 'confirm', bundleNo: number | string | null): void
}>()

const open = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })
const choice = ref<'free' | 'existing' | 'source'>('free')
const selectedBundleNo = ref<number | null>(null)
const selectedSourceIds = ref<number[]>([])

watch(open, (v) => { if (v) { choice.value = 'free'; selectedBundleNo.value = null; selectedSourceIds.value = [] } })

const opAmountDelta = computed(() => {
  const op = props.op
  if (!op) return 0
  const before = Number(op.before?.budget ?? op.before?.planned_amount ?? op.before?.amount ?? 0)
  const after = Number(op.after?.budget ?? op.after?.planned_amount ?? op.after?.amount ?? 0)
  return after - before
})

// Строки корректировки, где сумма СНИЖЕНА («снятие») — источник связки.
const availableSources = computed(() => {
  return props.ops
    .filter((o) => o.op_type === 'update' && o.id !== props.op?.id)
    .map((o) => {
      const before = Number(o.before?.budget ?? o.before?.planned_amount ?? o.before?.amount ?? 0)
      const after = Number(o.after?.budget ?? o.after?.planned_amount ?? o.after?.amount ?? 0)
      return { id: o.id, path: o.path || `#${o.target_id ?? o.target_ref}`, before, after }
    })
    .filter((s) => s.after < s.before - 0.005)
})

function toggleSource(id: number) {
  const i = selectedSourceIds.value.indexOf(id)
  if (i >= 0) selectedSourceIds.value.splice(i, 1)
  else selectedSourceIds.value.push(id)
}

const canConfirm = computed(() => {
  if (choice.value === 'free') return true
  if (choice.value === 'existing') return !!selectedBundleNo.value
  if (choice.value === 'source') return selectedSourceIds.value.length > 0
  return false
})

function confirm() {
  if (choice.value === 'free') { emit('confirm', null); open.value = false; return }
  if (choice.value === 'existing') { emit('confirm', selectedBundleNo.value); open.value = false; return }
  // Для «source» вызывающий компонент (RevisionDraftBar.vue) сам генерирует
  // новый bundle_no и проставляет его ЭТОЙ строке и выбранным source-строкам —
  // здесь мы только сообщаем выбор (через событие с особым префиксом).
  emit('confirm', `__sources__:${selectedSourceIds.value.join(',')}`)
  open.value = false
}
</script>

<style scoped>
.rev-bundle-list { max-height: 240px; overflow-y: auto; border: 1px solid var(--crm-border); border-radius: 6px; }
</style>
