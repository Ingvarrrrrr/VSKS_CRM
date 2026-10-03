<template>
  <v-alert
    v-for="match in group.existing_matches" :key="match.purchase_id"
    :type="match.kind === 'same_amount' ? 'info' : 'warning'" variant="tonal" density="compact"
    class="mt-2 fiem-alert"
  >
    <div class="d-flex justify-space-between align-start flex-wrap ga-2">
      <div>
        <div class="font-weight-medium">
          Такая закупка уже есть:
          <a href="#" @click.prevent="goToPurchase(match.purchase_id)">{{ match.registry_number || `#${match.purchase_id}` }}</a>
        </div>
        <div class="text-caption">
          {{ match.subject || match.name || '(без предмета)' }} — {{ match.contractor_name || '(без поставщика)' }}
          — {{ fmt(itemsTotal(match)) }} — <v-chip size="x-small" variant="tonal">{{ statusLabel(match.status) }}</v-chip>
        </div>
        <div class="text-caption text-medium-emphasis">
          {{ match.kind === 'same_amount' ? 'Тот же поставщик и сумма — скорее всего та же закупка.' : 'Тот же поставщик, другая сумма — возможно, та же закупка. Нужно решить.' }}
        </div>
      </div>
      <v-btn-toggle
        :model-value="actionFor(match)"
        density="compact" variant="outlined" mandatory
        @update:model-value="v => onAction(match, v)"
      >
        <v-btn value="same" size="small">Это она</v-btn>
        <v-btn value="new" size="small">Нет, создать из импорта</v-btn>
      </v-btn-toggle>
    </div>

    <template v-if="actionFor(match) === 'same'">
      <div class="d-flex ga-2 mt-2 flex-wrap">
        <v-btn size="x-small" variant="tonal" @click="applyAllUnboundToSuggested(group.key, match)">
          Всё на строку плана из файла
        </v-btn>
        <v-btn size="x-small" variant="tonal" @click="createPlannedForAllUnbound(group.key, match)">
          Создать плановые для всех непривязанных
        </v-btn>
      </div>

      <v-table density="compact" class="mt-2 fiem-items">
        <thead>
          <tr>
            <th>Позиция</th>
            <th>Кол-во</th>
            <th>Сумма</th>
            <th>Плановая позиция</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in match.items" :key="it.item_id">
            <td>{{ it.name }}</td>
            <td>{{ it.qty ?? '—' }}</td>
            <td>{{ fmt(it.total) }}</td>
            <td>
              <template v-if="it.feo_planned_item_id != null">
                <v-chip size="small" variant="tonal" prepend-icon="mdi-lock-outline">
                  {{ it.planned_item_name || `#${it.feo_planned_item_id}` }}
                </v-chip>
                <div class="text-caption text-medium-emphasis">уже привязана — не меняется</div>
              </template>
              <template v-else>
                <div class="d-flex align-center ga-1 flex-wrap">
                  <span v-if="linkFor(match, it).skip" class="text-caption text-medium-emphasis">не привязывать</span>
                  <span v-else-if="linkFor(match, it).create_planned" class="text-caption">создать плановую позицию</span>
                  <v-chip v-else-if="effectivePlannedId(match, it) != null" size="small" variant="tonal">
                    {{ plannedLabel(match, it) }}
                  </v-chip>
                  <span v-else class="text-caption text-medium-emphasis">не предложена — выберите</span>

                  <v-btn size="x-small" variant="text" @click="openPicker(match, it)">Выбрать</v-btn>
                  <v-btn size="x-small" variant="text" color="success"
                         @click="setExistingMatchItemCreatePlanned(group.key, match.purchase_id, it.item_id)">
                    Создать плановую
                  </v-btn>
                  <v-btn size="x-small" variant="text" color="warning"
                         @click="setExistingMatchItemSkip(group.key, match.purchase_id, it.item_id)">
                    Не привязывать
                  </v-btn>
                </div>
                <div v-if="it.category_change" class="text-caption text-medium-emphasis">
                  категория: {{ it.category_change.from || '—' }} → {{ it.category_change.to || '—' }}
                </div>
                <div v-if="it.warnings?.length" class="text-caption text-warning">
                  <div v-for="(w, i) in it.warnings" :key="i">{{ w }}</div>
                </div>
              </template>
            </td>
          </tr>
        </tbody>
      </v-table>
    </template>

    <v-dialog v-model="pickerOpen" max-width="900">
      <v-card>
        <v-card-title class="text-h6">Выбрать плановую позицию</v-card-title>
        <v-card-text>
          <FeoPlannedItemsSelect
            v-if="pickerItem"
            :model-value="pickerSelection"
            :category-id="null"
            :nodes="feoNodes"
            :items="plannedResiduals"
            :subsidy-id="subsidyId"
            @update:model-value="onPickerSelect"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="pickerOpen = false">Закрыть</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-alert>
</template>

<script setup lang="ts">
// Блок «Такая закупка уже есть» (план breezy-mixing-lovelace.md, Часть А) —
// под карточкой группы в FactImportStepGroups.vue. Пикер плановой позиции —
// тот же приём, что FactImportRowPlanPicker.vue (ПРАВИЛО №6): переиспользует
// FeoPlannedItemsSelect целиком, nodes/items грузятся один раз на мастер.
import { computed, ref } from 'vue'
import FeoPlannedItemsSelect from '@/components/items/FeoPlannedItemsSelect.vue'
import { useFeoLeaves } from '@/composables/useFeoLeaves'
import { useFeoPlannedResiduals, type FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import {
  useFactImport,
  type FactImportGroup,
  type FactImportExistingMatch,
  type FactImportExistingMatchItem,
} from '@/composables/subsidies/useFactImport'
// ПРАВИЛО №6: подпись статуса закупки и формат суммы — общие источники,
// не своя копия (match.status/match.items[].total — коды/числа с бэкенда).
import { purchaseStatusLabel } from '@/constants/purchaseStatus'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{ group: FactImportGroup; subsidyId: number | null }>()

const {
  factImport,
  existingMatchDecision,
  setExistingMatchAction,
  setExistingMatchItemPlanned,
  setExistingMatchItemCreatePlanned,
  setExistingMatchItemSkip,
  applyAllUnboundToSuggested,
  createPlannedForAllUnbound,
  queuePreviewRefresh,
} = useFactImport()

const subsidyIdRef = computed(() => props.subsidyId)
const { feoNodes } = useFeoLeaves({ subsidyId: subsidyIdRef })
const { plannedResiduals } = useFeoPlannedResiduals({ subsidyId: subsidyIdRef })

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return formatMoney(v)
}

function statusLabel(s?: string | null): string {
  return purchaseStatusLabel(s) || 'План закупок'
}

function itemsTotal(match: FactImportExistingMatch): number {
  return match.items.reduce((s, it) => s + (it.total || 0), 0)
}

// Открываем в новой вкладке (ПРАВИЛО №6 — тот же приём, что useFeoPlannedConsumers
// .goToPurchase) — этот блок висит внутри мастера импорта, уводить с него нельзя.
function goToPurchase(purchaseId: number) {
  window.open(`/orders/${purchaseId}`, '_blank')
}

/** 'same' по умолчанию, если группа предвыбрана (kind=same_amount) ИЛИ есть
 *  явное решение владельца; иначе 'new' (same_supplier без решения не идёт
 *  на коммит — needs_existing_decision, но в UI показываем переключатель
 *  без предвыбора). */
function actionFor(match: FactImportExistingMatch): 'same' | 'new' {
  const d = existingMatchDecision(props.group.key)
  if (d && d.purchase_id === match.purchase_id) return d.action
  return match.kind === 'same_amount' ? 'same' : 'new'
}

function onAction(match: FactImportExistingMatch, action: 'same' | 'new') {
  setExistingMatchAction(props.group.key, match.purchase_id, action)
  queuePreviewRefresh()
}

function linkFor(match: FactImportExistingMatch, it: FactImportExistingMatchItem) {
  const d = existingMatchDecision(props.group.key)
  if (d && d.purchase_id === match.purchase_id) {
    return d.item_links?.[String(it.item_id)] ?? {}
  }
  return {}
}

function effectivePlannedId(match: FactImportExistingMatch, it: FactImportExistingMatchItem): number | null {
  const link = linkFor(match, it)
  if (link.skip || link.create_planned) return null
  if (link.planned_item_id != null) return link.planned_item_id
  return it.suggested?.planned_item_id ?? null
}

function plannedLabel(match: FactImportExistingMatch, it: FactImportExistingMatchItem): string {
  const id = effectivePlannedId(match, it)
  if (id == null) return '—'
  const row = plannedResiduals.value.find(r => r.kind === 'planned_item' && r.id === id)
  return row?.name || `#${id}`
}

const pickerOpen = ref(false)
const pickerMatch = ref<FactImportExistingMatch | null>(null)
const pickerItem = ref<FactImportExistingMatchItem | null>(null)
const pickerSelection = computed<FeoPlanSelection | null>(() => {
  if (!pickerMatch.value || !pickerItem.value) return null
  const id = effectivePlannedId(pickerMatch.value, pickerItem.value)
  return id != null ? { kind: 'planned_item', id } : null
})

function openPicker(match: FactImportExistingMatch, it: FactImportExistingMatchItem) {
  pickerMatch.value = match
  pickerItem.value = it
  pickerOpen.value = true
}

function onPickerSelect(sel: FeoPlanSelection | null) {
  if (!pickerMatch.value || !pickerItem.value) return
  setExistingMatchItemPlanned(props.group.key, pickerMatch.value.purchase_id, pickerItem.value.item_id, sel?.id ?? null)
  queuePreviewRefresh()
}
</script>

<style scoped>
.fiem-alert :deep(.v-alert__content) { width: 100%; }
.fiem-items th, .fiem-items td { white-space: normal; }
</style>
