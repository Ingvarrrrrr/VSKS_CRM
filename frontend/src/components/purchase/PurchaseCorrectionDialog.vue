<template>
  <!-- Диалог корректировки категории ФЭО, плановых позиций и мероприятия действующей закупки -->
  <v-dialog
    :model-value="modelValue"
    max-width="860"
    persistent
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span class="d-flex align-center ga-2">
          <v-icon icon="mdi-file-edit-outline" color="amber-darken-2" />
          Корректировка закупки
        </span>
        <v-btn icon="mdi-close" size="small" variant="text" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-4" style="max-height: 75vh; overflow-y: auto;">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          При корректировке «на месте» статус и согласование закупки сохраняются без сброса.
          Если меняются категории ФЭО или плановые позиции, старые автосозданные позиции
          удаляются (деактивируются), в новых категориях создаются/подбираются новые и
          проверяется превышение сумм.
        </v-alert>

        <v-alert
          v-if="excessError"
          type="warning"
          variant="tonal"
          density="comfortable"
          class="mb-4"
        >
          <div class="font-weight-bold mb-1">Обнаружено превышение сумм при перераспределении</div>
          <div class="text-body-2 mb-3">{{ excessError }}</div>
          <div class="d-flex flex-wrap ga-2">
            <v-btn
              v-if="wishId && canReturnToDraft"
              size="small"
              color="primary"
              variant="flat"
              prepend-icon="mdi-undo-variant"
              :loading="returningToDraft"
              @click="returnToDraftWish"
            >
              Вернуть в черновик заявки №{{ wishId }} (на пересогласование)
            </v-btn>
            <v-btn
              size="small"
              color="warning"
              variant="outlined"
              :loading="saving"
              @click="submitCorrection(true)"
            >
              Всё равно сохранить (запросить согласование превышения)
            </v-btn>
          </div>
        </v-alert>

        <v-alert v-else-if="errorMessage" type="error" variant="tonal" density="compact" class="mb-4">
          {{ errorMessage }}
        </v-alert>

        <v-row dense>
          <v-col cols="12" md="6">
            <v-autocomplete
              v-model="localEventId"
              :items="events"
              item-title="name"
              item-value="id"
              label="Мероприятие"
              variant="outlined"
              density="compact"
              clearable
              hide-details="auto"
              no-data-text="Нет мероприятий в субсидии"
            />
          </v-col>
          <v-col cols="12" md="6" class="d-flex align-center">
            <v-switch
              v-model="localFeoPerItem"
              label="Разные категории ФЭО для каждого товара"
              density="compact"
              color="primary"
              hide-details
              @update:model-value="onTogglePerItem"
            />
          </v-col>
        </v-row>

        <div v-if="!localFeoPerItem && subsidyId && feoTreeNodes.length" class="mt-4">
          <div class="text-subtitle-2 mb-1">Общая категория ФЭО</div>
          <FeoTreeSelect
            v-model="localHeaderCatId"
            :nodes="feoTreeNodes"
            :leaves="feoLeaves"
            :root-label="rootLabel"
            :node-amounts="nodeAmounts"
            :plan-positions="plannedItems"
            :allow-unallocated="false"
            @update:model-value="onHeaderCategoryChange"
          />
        </div>

        <div v-if="localItems.length" class="mt-5">
          <div class="text-subtitle-2 font-weight-medium mb-2">
            Позиции закупки ({{ localItems.length }})
          </div>
          <v-card
            v-for="(it, idx) in localItems"
            :key="it.id"
            variant="outlined"
            class="pa-3 mb-2"
          >
            <div class="d-flex align-center justify-space-between flex-wrap ga-2 mb-2">
              <div class="font-weight-medium text-body-2">
                {{ idx + 1 }}. {{ it.item_name || 'Позиция без названия' }}
              </div>
              <div class="text-caption text-medium-emphasis">
                <template v-if="it.quantity != null">{{ it.quantity }} ед.</template>
                <template v-if="it.total_price != null"> · {{ formatMoney(Number(it.total_price)) }}</template>
              </div>
            </div>

            <v-row dense>
              <v-col v-if="localFeoPerItem && subsidyId && feoTreeNodes.length" cols="12">
                <FeoTreeSelect
                  v-model="it.feo_category_id"
                  :nodes="feoTreeNodes"
                  :leaves="feoLeaves"
                  :root-label="rootLabel"
                  :node-amounts="nodeAmounts"
                  :plan-positions="plannedItems"
                  horizontal
                  label="Категория ФЭО позиции"
                  @update:model-value="onItemCategoryChange(it)"
                />
              </v-col>
              <v-col cols="12">
                <v-autocomplete
                  v-model="it.feo_planned_item_id"
                  :items="plannedOptionsFor(effectiveItemCatId(it))"
                  item-title="name"
                  item-value="id"
                  label="Плановая позиция плана закупок (опционально)"
                  placeholder="Автоматически (создать/подобрать в выбранной категории)"
                  variant="outlined"
                  density="compact"
                  clearable
                  hide-details="auto"
                  no-data-text="Нет готовых плановых позиций — будет создана автоматически"
                >
                  <template #item="{ item, props: itemProps }">
                    <v-list-item v-bind="itemProps">
                      <template #subtitle>
                        <span>
                          План: {{ formatMoney(item.raw.planned_amount || 0) }} ·
                          Остаток: {{ formatMoney(item.raw.residual || 0) }}
                        </span>
                      </template>
                    </v-list-item>
                  </template>
                </v-autocomplete>
              </v-col>
            </v-row>
          </v-card>
        </div>

        <v-text-field
          v-model="localComment"
          label="Комментарий / причина корректировки (необязательно)"
          variant="outlined"
          density="compact"
          hide-details
          class="mt-4"
        />

        <!-- Рабочий откат в черновик исходной заявки -->
        <v-card v-if="wishId" variant="tonal" color="secondary" class="pa-3 mt-5">
          <div class="d-flex align-center justify-space-between flex-wrap ga-3">
            <div style="flex: 1; min-width: 240px;">
              <div class="text-subtitle-2 font-weight-bold mb-1">
                Возврат в черновик заявки №{{ wishId }}
              </div>
              <div class="text-caption text-medium-emphasis">
                Если нужно пересмотреть суммы, состав или заново согласовать заявку: закупка вернётся в черновик
                заявки, все позиции сохранят свои плановые позиции (они удалятся только если вы сами перенесёте их
                в другую категорию).
              </div>
              <div v-if="!canReturnToDraft" class="text-caption text-warning mt-1">
                Недоступно на текущей стадии закупки (после заключения договора/поставки используйте корректировку выше).
              </div>
            </div>
            <v-btn
              color="secondary"
              variant="flat"
              size="small"
              prepend-icon="mdi-undo-variant"
              :disabled="!canReturnToDraft || saving"
              :loading="returningToDraft"
              @click="returnToDraftWish"
            >
              Вернуть в черновик заявки
            </v-btn>
          </div>
        </v-card>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-3 justify-end ga-2">
        <v-btn variant="text" :disabled="saving || returningToDraft" @click="emit('update:modelValue', false)">
          Отмена
        </v-btn>
        <v-btn
          color="amber-darken-2"
          variant="flat"
          prepend-icon="mdi-check"
          :loading="saving"
          :disabled="returningToDraft"
          @click="submitCorrection(false)"
        >
          Сохранить корректировку
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import FeoTreeSelect from '@/components/items/FeoTreeSelect.vue'
import type { PurchaseCorrectionsSummary } from '@/components/purchase/PurchaseCorrectionHistoryDialog.vue'
import type { FeoLeaf, FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import { formatMoney } from '@/utils/formatMoney'

interface LocalCorrectionItem {
  id: number
  item_name: string
  quantity: number | null
  total_price: number | null
  feo_category_id: number | null
  feo_planned_item_id: number | null
}

const props = defineProps<{
  modelValue: boolean
  purchaseId: number
  wishId?: number | null
  purchaseStatus?: string | null
  subsidyId: number | null
  feoTreeNodes: FeoNode[]
  feoLeaves: FeoLeaf[]
  rootLabel?: string | null
  nodeAmounts?: Record<number, { budget: number; free: number }> | null
  events: Array<{ id: number; name: string }>
  plannedItems: FeoPlanPosition[]
  initialFeoCategoryId: number | null
  initialFeoPerItem: boolean
  initialEventId: number | null
  items: Array<any>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'saved', data: PurchaseCorrectionsSummary): void
  (e: 'returnedToDraft', wishId: number): void
}>()

const localHeaderCatId = ref<number | null>(null)
const localFeoPerItem = ref(false)
const localEventId = ref<number | null>(null)
const localItems = ref<LocalCorrectionItem[]>([])
const localComment = ref('')
const saving = ref(false)
const returningToDraft = ref(false)
const errorMessage = ref('')
const excessError = ref('')

const canReturnToDraft = computed(() =>
  !!props.wishId && ['wishes', 'plan_schedule', 'work_in_progress'].includes(props.purchaseStatus || ''),
)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    errorMessage.value = ''
    excessError.value = ''
    localComment.value = ''
    localHeaderCatId.value = props.initialFeoCategoryId
    localFeoPerItem.value = props.initialFeoPerItem
    localEventId.value = props.initialEventId
    localItems.value = (props.items || [])
      .filter((it: any) => it.id != null)
      .map((it: any) => ({
        id: Number(it.id),
        item_name: it.item_name || '',
        quantity: it.quantity != null ? Number(it.quantity) : null,
        total_price: it.total_price != null ? Number(it.total_price) : null,
        feo_category_id: it.feo_category_id ?? props.initialFeoCategoryId ?? null,
        feo_planned_item_id: it.feo_planned_item_id ?? null,
      }))
  },
)

function effectiveItemCatId(it: LocalCorrectionItem): number | null {
  return localFeoPerItem.value ? (it.feo_category_id ?? localHeaderCatId.value) : localHeaderCatId.value
}

function plannedOptionsFor(catId: number | null): FeoPlanPosition[] {
  const all = (props.plannedItems || []).filter(p => p.kind === 'planned_item')
  if (catId == null) return all
  return all.filter(p => p.category_id === catId || (p.ancestor_ids || []).includes(catId))
}

function clearIncompatiblePlannedItem(it: LocalCorrectionItem, targetCatId: number | null) {
  if (it.feo_planned_item_id == null || targetCatId == null) return
  const opts = plannedOptionsFor(targetCatId)
  if (!opts.some(p => p.id === it.feo_planned_item_id)) {
    it.feo_planned_item_id = null
  }
}

function onTogglePerItem(val: boolean | null) {
  const perItem = !!val
  if (perItem) {
    for (const it of localItems.value) {
      if (it.feo_category_id == null) {
        it.feo_category_id = localHeaderCatId.value
      }
    }
  } else {
    if (localHeaderCatId.value == null) {
      const firstCat = localItems.value.find(it => it.feo_category_id != null)?.feo_category_id ?? null
      localHeaderCatId.value = firstCat
    }
    for (const it of localItems.value) {
      it.feo_category_id = localHeaderCatId.value
      clearIncompatiblePlannedItem(it, localHeaderCatId.value)
    }
  }
}

function onHeaderCategoryChange(newCatId: number | null) {
  for (const it of localItems.value) {
    it.feo_category_id = newCatId
    clearIncompatiblePlannedItem(it, newCatId)
  }
}

function onItemCategoryChange(it: LocalCorrectionItem) {
  clearIncompatiblePlannedItem(it, it.feo_category_id)
}

async function submitCorrection(allowExcess = false) {
  if (!localFeoPerItem.value && localHeaderCatId.value == null && props.subsidyId) {
    errorMessage.value = 'Выберите общую категорию ФЭО'
    return
  }
  saving.value = true
  errorMessage.value = ''
  if (!allowExcess) excessError.value = ''
  try {
    const payload = {
      feo_category_id: localFeoPerItem.value ? null : localHeaderCatId.value,
      feo_per_item: localFeoPerItem.value,
      event_id: localEventId.value,
      comment: localComment.value.trim() || null,
      allow_excess: allowExcess,
      items: localItems.value.map(it => ({
        id: it.id,
        feo_category_id: localFeoPerItem.value ? it.feo_category_id : localHeaderCatId.value,
        feo_planned_item_id: it.feo_planned_item_id,
      })),
    }
    const res = await apiFetch<PurchaseCorrectionsSummary>(`/purchases/${props.purchaseId}/correction`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    emit('saved', res)
    emit('update:modelValue', false)
  } catch (e: any) {
    if (e?.payload?.code === 'CORRECTION_CAUSES_EXCESS') {
      excessError.value = e?.payload?.message || e?.detail || 'Перераспределение вызывает превышение сумм'
    } else {
      errorMessage.value =
        e?.payload?.message ||
        (typeof e?.detail === 'string' ? e.detail : null) ||
        e?.message ||
        'Не удалось сохранить корректировку'
    }
  } finally {
    saving.value = false
  }
}

async function returnToDraftWish() {
  if (!props.wishId || !canReturnToDraft.value) return
  if (!confirm(`Вернуть закупку в черновик заявки №${props.wishId}?\n\nСогласование будет сброшено, а все позиции останутся на своих плановых позициях.`)) {
    return
  }
  returningToDraft.value = true
  errorMessage.value = ''
  excessError.value = ''
  try {
    await apiFetch(`/purchases/${props.purchaseId}/return-to-draft-wish`, {
      method: 'POST',
      body: JSON.stringify({ comment: localComment.value.trim() || null }),
    })
    emit('update:modelValue', false)
    emit('returnedToDraft', props.wishId)
  } catch (e: any) {
    errorMessage.value =
      e?.payload?.message ||
      (typeof e?.detail === 'string' ? e.detail : null) ||
      e?.message ||
      'Не удалось вернуть закупку в черновик заявки'
  } finally {
    returningToDraft.value = false
  }
}
</script>
