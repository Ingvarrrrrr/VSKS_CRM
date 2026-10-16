<template>
  <v-dialog :model-value="modelValue" max-width="560" @update:model-value="onDialogToggle">
    <v-card>
      <v-card-title class="pa-4 pb-2 d-flex align-center ga-2">
        <v-icon color="primary">mdi-content-copy</v-icon>
        Скопировать в субсидию…
      </v-card-title>
      <v-card-text class="pa-4 pt-0">
        <v-select
          v-model="targetSubsidyId"
          :items="targetOptions"
          item-title="name" item-value="id"
          label="Целевая субсидия" variant="outlined" density="compact"
          :disabled="transfer.loadingPreview.value || applyingChoice"
          @update:model-value="onTargetChange"
        />

        <div v-if="transfer.loadingPreview.value" class="d-flex align-center ga-2 py-3">
          <v-progress-circular indeterminate size="22" />
          <span class="text-body-2">Сравниваем закупки…</span>
        </div>

        <v-alert v-else-if="transfer.previewError.value" type="error" variant="tonal" density="compact">
          {{ transfer.previewError.value }}
        </v-alert>

        <template v-else-if="row">
          <v-alert v-if="row.state === 'same'" type="warning" variant="tonal" density="compact" class="mt-2">
            В субсидии «{{ targetName }}» уже есть {{ row.match?.registry_number }} на ту же сумму у
            того же поставщика. Не переносить?
          </v-alert>
          <v-alert v-else-if="row.state === 'amount_only'" type="warning" variant="tonal" density="compact" class="mt-2">
            В «{{ targetName }}» есть {{ row.match?.registry_number }} на ту же сумму, но поставщик
            другой ({{ row.match?.contractor_name || '—' }} вместо {{ row.source.contractor_name || '—' }}).
            Может, ошибка при заведении?
            <div class="mt-1">
              <a href="#" @click.prevent="openMatchInNewTab">Открыть её</a>
            </div>
          </v-alert>
          <v-alert v-else type="info" variant="tonal" density="compact" class="mt-2">
            В субсидии «{{ targetName }}» этой закупки нет — можно скопировать как новую.
          </v-alert>
        </template>

        <v-alert v-if="resultText" type="success" variant="tonal" density="compact" class="mt-3">
          {{ resultText }}
          <div v-if="resultLinkId" class="mt-1">
            <a href="#" @click.prevent="openOrderInNewTab(resultLinkId)">Открыть</a>
          </div>
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0 flex-wrap ga-2">
        <template v-if="row && !resultText">
          <template v-if="row.state === 'same'">
            <v-btn size="small" variant="text" :disabled="applyingChoice" @click="close">Не переносить</v-btn>
            <v-btn size="small" variant="tonal" color="primary" :loading="applyingChoice" @click="choose('merge')">
              Дополнить её файлами и исполнителем
            </v-btn>
            <v-btn size="small" variant="outlined" :loading="applyingChoice" @click="choose('copy')">
              Всё равно скопировать
            </v-btn>
          </template>
          <template v-else-if="row.state === 'amount_only'">
            <v-btn size="small" variant="text" :disabled="applyingChoice" @click="close">Отмена</v-btn>
            <v-btn size="small" variant="tonal" color="primary" :loading="applyingChoice" @click="choose('merge')">
              Это она — дополнить
            </v-btn>
            <v-btn size="small" variant="outlined" :loading="applyingChoice" @click="choose('copy')">
              Скопировать как новую
            </v-btn>
          </template>
          <template v-else>
            <v-spacer />
            <v-btn size="small" variant="text" :disabled="applyingChoice" @click="close">Отмена</v-btn>
            <v-btn size="small" variant="flat" color="primary" :loading="applyingChoice" @click="choose('copy')">
              Скопировать
            </v-btn>
          </template>
        </template>
        <template v-else>
          <v-spacer />
          <v-btn size="small" variant="text" @click="close">Закрыть</v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
// Копирование ОДНОЙ закупки в другую субсидию — кнопка в PurchaseHeader.vue
// (карточка закупки). Composable usePurchaseTransfer.ts — общий с диалогом
// переноса целой субсидии (SubsidyTransferPurchasesDialog.vue, ПРАВИЛО №6),
// здесь только разметка под сценарий «одна закупка».
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { usePurchaseTransfer, type PurchaseTransferAction } from '@/composables/purchaseTransfer/usePurchaseTransfer'
import { useToast } from '@/composables/useToast'

const props = defineProps<{
  modelValue: boolean
  purchaseId: number | null
  sourceSubsidyId: number | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'done'): void
}>()

const toast = useToast()
const transfer = usePurchaseTransfer()

interface SubsidyOption { id: number; name: string }
const targetOptions = ref<SubsidyOption[]>([])
const targetSubsidyId = ref<number | null>(null)
const applyingChoice = ref(false)
const resultText = ref('')
const resultLinkId = ref<number | null>(null)

const row = computed(() => transfer.preview.value?.rows?.[0] ?? null)
const targetName = computed(() => transfer.preview.value?.target_subsidy?.name || '')

async function loadTargetOptions() {
  try {
    const all = await apiFetch<SubsidyOption[]>('/subsidies/')
    targetOptions.value = all.filter(s => s.id !== props.sourceSubsidyId)
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось загрузить список субсидий' }), 'error')
  }
}

watch(() => props.modelValue, (v) => {
  if (v) {
    targetSubsidyId.value = null
    resultText.value = ''
    resultLinkId.value = null
    transfer.preview.value = null
    loadTargetOptions()
  }
})

async function onTargetChange(id: number | null) {
  resultText.value = ''
  resultLinkId.value = null
  const pid = props.purchaseId
  const sid = props.sourceSubsidyId
  if (!id || !pid || !sid) return
  try {
    await transfer.loadPreview(sid, id, [pid])
  } catch {
    // previewError уже показан через transfer.previewError
  }
}

async function choose(action: PurchaseTransferAction) {
  if (!row.value || !targetSubsidyId.value) return
  transfer.setAction(row.value.source.id, action)
  if (action === 'merge' && !transfer.targetPurchaseIdOf(row.value.source.id) && row.value.match) {
    transfer.setTargetPurchase(row.value.source.id, row.value.match.id)
  }
  applyingChoice.value = true
  try {
    const result = await transfer.apply(targetSubsidyId.value, { onlySourceIds: [row.value.source.id] })
    const c = result.copied[0]
    const m = result.merged[0]
    if (c) {
      resultText.value = `Скопировано: ${c.new_registry_number}`
      resultLinkId.value = c.new_id
      toast.addToast(resultText.value, 'success')
    } else if (m) {
      resultText.value = `Дополнено: ${m.target_registry_number}`
      resultLinkId.value = m.target_id
      toast.addToast(resultText.value, 'success')
    } else if (result.warnings?.length) {
      resultText.value = result.warnings.join('; ')
      toast.addToast(resultText.value, 'warning')
    } else {
      resultText.value = 'Готово'
    }
    emit('done')
  } catch (e: any) {
    toast.addToast(describeApiError(e, { fallback: 'Не удалось скопировать закупку' }), 'error')
  } finally {
    applyingChoice.value = false
  }
}

function openOrderInNewTab(id: number) {
  window.open(`/orders/${id}/edit`, '_blank', 'noopener')
}
function openMatchInNewTab() {
  if (row.value?.match) openOrderInNewTab(row.value.match.id)
}

function close() {
  emit('update:modelValue', false)
}
function onDialogToggle(v: boolean) {
  emit('update:modelValue', v)
}
</script>
