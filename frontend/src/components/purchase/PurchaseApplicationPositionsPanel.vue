<template>
  <div class="positions-panel my-2">
    <!-- Сворачиваемая плашка со сводкой позиций и аналогов -->
    <v-card variant="outlined" density="compact" class="bg-grey-lighten-5">
      <div
        class="d-flex align-center justify-space-between px-3 py-2 cursor-pointer select-none"
        @click="expanded = !expanded"
      >
        <div class="d-flex align-center gap-2 flex-wrap">
          <v-icon :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="20" color="deep-purple" />
          <span class="text-caption font-weight-bold">
            Позиции и аналоги товаров ({{ positions.length }} поз.)
          </span>
          <v-chip v-if="rejectedCount > 0" size="x-small" color="error" variant="flat" class="font-weight-bold">
            Не подходят: {{ rejectedCount }}
          </v-chip>
          <v-chip v-else-if="analogsCount > 0" size="x-small" color="indigo" variant="tonal">
            Предложены аналоги: {{ analogsCount }}
          </v-chip>
          <v-chip v-else-if="positions.length > 0" size="x-small" color="success" variant="tonal">
            Все по ТЗ
          </v-chip>
        </div>

        <div class="d-flex align-center gap-2">
          <span v-if="positionsTotal > 0" class="text-caption text-medium-emphasis">
            Сумма поз.: <strong>{{ formatMoney(positionsTotal) }} ₽</strong>
          </span>
          <v-btn
            v-if="editable && positionsTotal > 0 && Math.abs(positionsTotal - currentAppPrice) > 0.01"
            size="x-small"
            color="deep-purple"
            variant="tonal"
            title="Записать сумму позиций в общую цену заявки"
            @click.stop="applyTotalToApp"
          >
            Применить сумму
          </v-btn>
        </div>
      </div>

      <!-- Раскрывающаяся таблица позиций -->
      <v-expand-transition>
        <div v-if="expanded" class="pa-2 border-top">
          <div v-if="!positions.length" class="text-caption text-medium-emphasis py-2 text-center">
            Позиции ещё не подгружены. Нажмите «Инициализировать позиции» или прикрепите ТКП участника.
          </div>

          <v-table v-else density="compact" class="positions-table text-caption">
            <thead>
              <tr>
                <th style="width: 32px">№</th>
                <th style="width: 28%">Требование по ТЗ</th>
                <th style="width: 32%">Предложение участника (аналог)</th>
                <th style="width: 18%">Цена и сумма</th>
                <th style="width: 22%">Решение комиссии</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(pos, pIdx) in localPositions"
                :key="pIdx"
                :class="{
                  'bg-red-lighten-5': pos.compliance_status === 'analog_rejected',
                  'bg-indigo-lighten-5': pos.compliance_status === 'analog_accepted',
                }"
              >
                <!-- Номер -->
                <td class="font-weight-bold text-medium-emphasis">{{ pos.item_num || (pIdx + 1) }}</td>

                <!-- Требование по нашему ТЗ -->
                <td>
                  <div class="font-weight-medium">{{ pos.requested_name || 'Товар ' + (pIdx + 1) }}</div>
                  <div v-if="pos.requested_specs" class="text-grey-darken-1 specs-preview">
                    {{ pos.requested_specs }}
                  </div>
                  <div class="text-grey text-caption">
                    Кол-во: {{ pos.quantity }} {{ pos.unit || 'шт.' }}
                  </div>
                </td>

                <!-- Предложение участника -->
                <td>
                  <v-text-field
                    v-model="pos.offered_name"
                    placeholder="Модель / наименование товара"
                    variant="outlined"
                    density="compact"
                    hide-details
                    class="mb-1 text-caption-field"
                    @update:model-value="onPosFieldChange(pos)"
                  />
                  <div class="d-flex align-center justify-space-between">
                    <v-checkbox
                      v-model="pos.is_alternative"
                      label="Предложен аналог"
                      density="compact"
                      color="indigo"
                      hide-details
                      class="analog-checkbox"
                      @update:model-value="onAlternativeToggle(pos)"
                    />
                    <span v-if="pos.is_alternative" class="text-caption text-indigo font-weight-medium">
                      Эквивалент
                    </span>
                  </div>
                </td>

                <!-- Цена, НДС и сумма -->
                <td>
                  <div class="d-flex align-center gap-1 mb-1">
                    <v-text-field
                      v-model.number="pos.unit_price"
                      label="За ед., ₽"
                      type="number"
                      variant="outlined"
                      density="compact"
                      hide-details
                      class="text-caption-field"
                      @update:model-value="onUnitPriceChange(pos)"
                    />
                  </div>
                  <div class="mb-1">
                    <v-select
                      v-model="pos.vat_rate"
                      :items="['Без НДС', '20%', '22%', '10%', '5%', '7%']"
                      label="НДС позиции"
                      variant="outlined"
                      density="compact"
                      hide-details
                      class="text-caption-field"
                      @update:model-value="onPosFieldChange(pos)"
                    />
                  </div>
                  <div class="text-caption text-medium-emphasis">
                    Сумма: <strong>{{ formatMoney(pos.total_price) }} ₽</strong>
                  </div>
                </td>

                <!-- Решение комиссии по позиции -->
                <td>
                  <v-btn-toggle
                    v-model="pos.compliance_status"
                    mandatory
                    density="compact"
                    rounded="md"
                    class="w-100 mb-1 btn-toggle-compact"
                    @update:model-value="onComplianceChange(pos)"
                  >
                    <v-btn value="compliant" size="x-small" color="success" variant="tonal" title="По ТЗ Заказчика">
                      ТЗ
                    </v-btn>
                    <v-btn value="analog_accepted" size="x-small" color="indigo" variant="tonal" title="Аналог подходит">
                      Принят
                    </v-btn>
                    <v-btn value="analog_rejected" size="x-small" color="error" variant="tonal" title="Аналог НЕ подходит">
                      Отклонён
                    </v-btn>
                  </v-btn-toggle>

                  <!-- Комментарий причины несоответствия аналога -->
                  <v-text-field
                    v-if="pos.compliance_status === 'analog_rejected'"
                    v-model="pos.compliance_note"
                    placeholder="Причина (напр. 11 л вместо 15 л)"
                    variant="outlined"
                    density="compact"
                    hide-details
                    class="text-caption-field bg-white"
                    @update:model-value="emitCompliance"
                  />
                </td>
              </tr>
            </tbody>
          </v-table>
        </div>
      </v-expand-transition>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { formatMoney } from '@/utils/formatMoney'

const props = withDefaults(
  defineProps<{
    positions: Array<any>
    appAdmitted: boolean
    currentAppPrice?: number
    editable?: boolean
  }>(),
  {
    currentAppPrice: 0,
    editable: true,
  }
)

const emit = defineEmits<{
  (e: 'update:positions', val: Array<any>): void
  (e: 'update:compliance', payload: { admitted: boolean; rejection_reason: string; decision_text: string }): void
  (e: 'apply-price', price: number): void
}>()

const expanded = ref(false)
const localPositions = ref<Array<any>>([])

watch(
  () => props.positions,
  (val) => {
    localPositions.value = Array.isArray(val) ? JSON.parse(JSON.stringify(val)) : []
  },
  { immediate: true, deep: true }
)

const analogsCount = computed(() => {
  return localPositions.value.filter((p) => p.is_alternative || p.compliance_status === 'analog_accepted').length
})

const rejectedCount = computed(() => {
  return localPositions.value.filter((p) => p.compliance_status === 'analog_rejected').length
})

const positionsTotal = computed(() => {
  return localPositions.value.reduce((acc, p) => acc + (Number(p.total_price) || 0), 0)
})

function onUnitPriceChange(pos: any) {
  const qty = Number(pos.quantity) || 1
  const price = Number(pos.unit_price) || 0
  pos.total_price = Math.round(qty * price * 100) / 100
  emitPositions()
}

function onPosFieldChange(pos: any) {
  emitPositions()
}

function onAlternativeToggle(pos: any) {
  if (pos.is_alternative && pos.compliance_status === 'compliant') {
    pos.compliance_status = 'analog_accepted'
  } else if (!pos.is_alternative && pos.compliance_status === 'analog_accepted') {
    pos.compliance_status = 'compliant'
  }
  emitPositions()
  emitCompliance()
}

function onComplianceChange(pos: any) {
  if (pos.compliance_status === 'analog_accepted' || pos.compliance_status === 'analog_rejected') {
    pos.is_alternative = true
  }
  emitPositions()
  emitCompliance()
}

function emitPositions() {
  emit('update:positions', localPositions.value)
}

function emitCompliance() {
  const rejected = localPositions.value.filter((p) => p.compliance_status === 'analog_rejected')
  const acceptedAnalogs = localPositions.value.filter((p) => p.compliance_status === 'analog_accepted')

  if (rejected.length > 0) {
    const pts = rejected.map((p, idx) => `п. ${p.item_num || idx + 1}`)
    const notes = rejected
      .map((p, idx) => {
        const note = (p.compliance_note || '').trim()
        return note ? `п. ${p.item_num || idx + 1}: ${note}` : ''
      })
      .filter(Boolean)

    let reason = `Предложены аналоги, которые не соответствуют техническому заданию (${pts.join(', ')})`
    if (notes.length > 0) {
      reason += `. Замечания: ${notes.join('; ')}`
    }

    emit('update:compliance', {
      admitted: false,
      rejection_reason: reason,
      decision_text: `Не соответствует. ${reason}`,
    })
  } else {
    // Если все приняты
    let decisionText = 'Признать соответствующей требованиям закупочной документации.'
    if (acceptedAnalogs.length > 0) {
      const pts = acceptedAnalogs.map((p, idx) => `п. ${p.item_num || idx + 1}`)
      decisionText += ` (предложен эквивалент по ${pts.join(', ')})`
    }
    emit('update:compliance', {
      admitted: true,
      rejection_reason: '',
      decision_text: decisionText,
    })
  }
}

function applyTotalToApp() {
  if (positionsTotal.value > 0) {
    emit('apply-price', positionsTotal.value)
  }
}
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}
.select-none {
  user-select: none;
}
.border-top {
  border-top: 1px solid #e0e0e0;
}
.specs-preview {
  font-size: 11px;
  max-height: 38px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.text-caption-field :deep(.v-field__input) {
  font-size: 11.5px !important;
  padding-top: 4px !important;
  padding-bottom: 4px !important;
  min-height: 28px !important;
}
.btn-toggle-compact {
  height: 26px !important;
}
.analog-checkbox :deep(.v-label) {
  font-size: 11px !important;
}
</style>
