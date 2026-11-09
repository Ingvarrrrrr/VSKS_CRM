<template>
  <div class="positions-panel my-2">
    <v-card variant="outlined" density="compact" class="bg-grey-lighten-5">
      <div class="d-flex align-center justify-space-between px-3 py-2 cursor-pointer select-none" @click="expanded = !expanded">
        <div class="d-flex align-center gap-2 flex-wrap">
          <v-icon :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="20" color="deep-purple" />
          <span class="text-caption font-weight-bold">Позиции и характеристики ({{ positions.length }} поз.)</span>
          <v-chip v-if="rejectedCount > 0" size="x-small" color="error" variant="flat" class="font-weight-bold">Не подходят: {{ rejectedCount }}</v-chip>
          <v-chip v-else-if="tzWarningCount > 0" size="x-small" color="orange-darken-2" variant="tonal">Уточнение ТЗ: {{ tzWarningCount }}</v-chip>
          <v-chip v-else-if="analogsCount > 0" size="x-small" color="indigo" variant="tonal">Аналоги: {{ analogsCount }}</v-chip>
          <v-chip v-else-if="positions.length > 0" size="x-small" color="success" variant="tonal">Все по ТЗ</v-chip>
        </div>
        <div class="d-flex align-center gap-2">
          <v-btn
            v-if="editable && positions.length > 0"
            size="x-small"
            color="deep-purple"
            variant="text"
            prepend-icon="mdi-auto-fix"
            title="Автоподстановка модели и параметров по ТЗ Заказчика"
            @click.stop="fillAllFromTz"
          >
            Модель по ТЗ
          </v-btn>
          <span v-if="positionsTotal > 0" class="text-caption text-medium-emphasis">Сумма: <strong>{{ formatMoney(positionsTotal) }} ₽</strong></span>
          <v-btn v-if="editable && positionsTotal > 0 && Math.abs(positionsTotal - currentAppPrice) > 0.01" size="x-small" color="deep-purple" variant="tonal" @click.stop="applyTotalToApp">Применить сумму</v-btn>
        </div>
      </div>

      <v-expand-transition>
        <div v-if="expanded" class="pa-2 border-top">
          <div v-if="!positions.length" class="text-caption text-medium-emphasis py-2 text-center">Позиции ещё не подгружены.</div>
          <v-table v-else density="compact" class="positions-table text-caption">
            <thead>
              <tr>
                <th style="width: 32px">№</th>
                <th style="width: 26%">Требование по ТЗ</th>
                <th style="width: 30%">Предложение участника (аналог)</th>
                <th style="width: 18%">Цена и сумма</th>
                <th style="width: 24%">Решение комиссии</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(pos, pIdx) in localPositions" :key="pIdx">
                <tr :class="{
                  'bg-red-lighten-5': pos.compliance_status === 'analog_rejected',
                  'bg-orange-lighten-5': pos.compliance_status === 'tz_warning' || pos.has_tz_correction,
                  'bg-indigo-lighten-5': pos.compliance_status === 'analog_accepted'
                }">
                  <td class="font-weight-bold text-medium-emphasis">{{ pos.item_num || (pIdx + 1) }}</td>
                  <td>
                    <div class="font-weight-medium">{{ pos.requested_name || 'Товар ' + (pIdx + 1) }}</div>
                    <div v-if="pos.requested_specs" class="text-grey-darken-1 specs-preview">{{ pos.requested_specs }}</div>
                    <div class="text-grey text-caption d-flex align-center justify-space-between mt-1">
                      <span>{{ pos.quantity }} {{ pos.unit || 'шт.' }}</span>
                      <v-btn v-if="pos.characteristics && pos.characteristics.length" size="x-small" variant="text" color="indigo" class="px-1" @click="pos._show_chars = !pos._show_chars">
                        {{ pos.characteristics.length }} характ. <v-icon end :icon="pos._show_chars ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="14" />
                      </v-btn>
                    </div>
                  </td>
                  <td>
                    <v-text-field v-model="pos.offered_name" placeholder="Модель / марка товара" variant="outlined" density="compact" hide-details class="mb-1 text-caption-field" @update:model-value="emitPositions()" />
                    <div class="d-flex align-center justify-space-between">
                      <v-checkbox v-model="pos.is_alternative" label="Аналог" density="compact" color="indigo" hide-details class="analog-checkbox" @update:model-value="onAlternativeToggle(pos)" />
                      <v-btn size="x-small" variant="text" color="indigo" prepend-icon="mdi-format-list-checks" @click="pos._show_chars = !pos._show_chars">Параметры</v-btn>
                    </div>
                  </td>
                  <td>
                    <v-text-field v-model.number="pos.unit_price" label="За ед., ₽" type="number" variant="outlined" density="compact" hide-details class="text-caption-field mb-1" @update:model-value="onUnitPriceChange(pos)" />
                    <v-select v-model="pos.vat_rate" :items="['Без НДС', '20%', '22%', '10%', '5%', '7%']" label="НДС" variant="outlined" density="compact" hide-details class="text-caption-field mb-1" @update:model-value="emitPositions()" />
                    <div class="text-caption text-medium-emphasis">Сумма: <strong>{{ formatMoney(pos.total_price) }} ₽</strong></div>
                  </td>
                  <td>
                    <v-btn-toggle v-model="pos.compliance_status" mandatory density="compact" rounded="md" class="w-100 mb-1 btn-toggle-compact" @update:model-value="onComplianceChange(pos)">
                      <v-btn value="compliant" size="x-small" color="success" variant="tonal">ТЗ</v-btn>
                      <v-btn value="tz_warning" size="x-small" color="orange-darken-2" variant="tonal" title="Модель по ТЗ с уточнением (опечатка в ТЗ)">Уточнение ТЗ</v-btn>
                      <v-btn value="analog_accepted" size="x-small" color="indigo" variant="tonal">Принят</v-btn>
                      <v-btn value="analog_rejected" size="x-small" color="error" variant="tonal">Отклонён</v-btn>
                    </v-btn-toggle>
                    <v-text-field
                      v-if="pos.compliance_status === 'analog_rejected' || pos.compliance_status === 'tz_warning'"
                      v-model="pos.compliance_note"
                      :placeholder="pos.compliance_status === 'tz_warning' ? 'Примечание об уточнении ТЗ' : 'Причина (напр. 11 л вместо 15 л)'"
                      variant="outlined"
                      density="compact"
                      hide-details
                      class="text-caption-field bg-white"
                      @update:model-value="emitCompliance"
                    />
                  </td>
                </tr>

                <!-- Вложенная таблица характеристик позиции -->
                <tr v-if="pos._show_chars" class="bg-grey-lighten-4">
                  <td colspan="5" class="pa-2">
                    <div class="d-flex align-center justify-space-between mb-1">
                      <span class="font-weight-bold text-caption text-indigo">Характеристики «{{ pos.requested_name }}»:</span>
                      <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-plus" @click="addCharRow(pos)">+ Параметр</v-btn>
                    </div>
                    <v-table v-if="pos.characteristics && pos.characteristics.length" density="compact" class="bg-white rounded border">
                      <thead>
                        <tr>
                          <th style="width: 32%">Параметр</th>
                          <th style="width: 25%">Требование ТЗ</th>
                          <th style="width: 28%">Предложение участника</th>
                          <th style="width: 15%">Статус</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(ch, cIdx) in pos.characteristics" :key="cIdx">
                          <td class="font-weight-medium text-caption">{{ ch.name }}</td>
                          <td class="text-caption text-medium-emphasis">{{ ch.req_value }} <span v-if="ch.unit" class="text-grey">{{ ch.unit }}</span></td>
                          <td>
                            <v-text-field v-model="ch.offered_value" placeholder="Предложенное значение" density="compact" variant="outlined" hide-details class="text-caption-field bg-yellow-lighten-5" @update:model-value="onCharValueChange(pos, ch)" />
                          </td>
                          <td>
                            <v-chip v-if="ch.tz_corrected_by_supplier" size="x-small" color="orange-darken-2" variant="flat">⚠️ Уточнение</v-chip>
                            <v-chip v-else-if="ch.compliant === false" size="x-small" color="error" variant="flat">✗ Не соотв.</v-chip>
                            <v-chip v-else-if="ch.is_changed" size="x-small" color="primary" variant="tonal">✓ Аналог</v-chip>
                            <v-chip v-else size="x-small" color="success" variant="tonal">✓ По ТЗ</v-chip>
                          </td>
                        </tr>
                      </tbody>
                    </v-table>
                  </td>
                </tr>
              </template>
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
  defineProps<{ positions: Array<any>; appAdmitted: boolean; currentAppPrice?: number; editable?: boolean }>(),
  { currentAppPrice: 0, editable: true }
)

const emit = defineEmits<{
  (e: 'update:positions', val: Array<any>): void
  (e: 'update:compliance', payload: { admitted: boolean; rejection_reason: string; decision_text: string }): void
  (e: 'apply-price', price: number): void
}>()

const expanded = ref(false)
const localPositions = ref<Array<any>>([])

watch(() => props.positions, (val) => {
  localPositions.value = Array.isArray(val) ? JSON.parse(JSON.stringify(val)) : []
}, { immediate: true, deep: true })

const analogsCount = computed(() => localPositions.value.filter((p) => p.is_alternative || p.compliance_status === 'analog_accepted').length)
const rejectedCount = computed(() => localPositions.value.filter((p) => p.compliance_status === 'analog_rejected').length)
const tzWarningCount = computed(() => localPositions.value.filter((p) => p.compliance_status === 'tz_warning' || p.has_tz_correction).length)
const positionsTotal = computed(() => localPositions.value.reduce((acc, p) => acc + (Number(p.total_price) || 0), 0))

function fillAllFromTz() {
  for (const pos of localPositions.value) {
    pos.is_exact_model_offer = true
    pos.is_alternative = false
    pos.compliance_status = 'compliant'
    pos.compliance_note = ''
    if (!pos.offered_name || pos.offered_name === 'По ТЗ') {
      pos.offered_name = pos.requested_name
    }
    for (const ch of (pos.characteristics || [])) {
      ch.offered_value = ch.ref_value || ch.req_value
      ch.compliant = true
      ch.is_changed = false
      ch.note = ''
      ch.tz_corrected_by_supplier = false
    }
  }
  emitPositions()
  emitCompliance()
}

function onUnitPriceChange(pos: any) {
  pos.total_price = Math.round((Number(pos.quantity) || 1) * (Number(pos.unit_price) || 0) * 100) / 100
  emitPositions()
}

function onAlternativeToggle(pos: any) {
  pos.compliance_status = pos.is_alternative ? 'analog_accepted' : 'compliant'
  emitPositions()
  emitCompliance()
}

function onComplianceChange(pos: any) {
  if (pos.compliance_status === 'analog_accepted' || pos.compliance_status === 'analog_rejected') {
    pos.is_alternative = true
    pos.is_exact_model_offer = false
  } else if (pos.compliance_status === 'tz_warning') {
    pos.is_exact_model_offer = true
    pos.has_tz_correction = true
    pos.is_alternative = false
  } else {
    pos.is_alternative = false
  }
  emitPositions()
  emitCompliance()
}

function evaluateCharClient(char: any) {
  const reqStr = (char.req_value || '').replace(/\xa0/g, ' ').replace(',', '.').trim()
  const offStr = (char.offered_value || '').replace(/\xa0/g, ' ').replace(',', '.').trim()
  const unit = char.unit ? ` ${char.unit}` : ''

  if (!offStr || offStr.toLowerCase() === reqStr.toLowerCase()) {
    char.compliant = true
    char.is_changed = false
    char.note = ''
    return
  }

  char.is_changed = true
  const offNum = parseFloat(offStr)
  const mRange = reqStr.match(/(?:от\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:до|\.\.\.|…|[-—–])\s*([+-]?\d+(?:\.\d+)?)/i)
  if (mRange && (reqStr.includes('до') || reqStr.includes('-') || reqStr.includes('…') || reqStr.includes('..'))) {
    const minV = Math.min(parseFloat(mRange[1]), parseFloat(mRange[2]))
    const maxV = Math.max(parseFloat(mRange[1]), parseFloat(mRange[2]))
    char.compliant = !isNaN(offNum) && offNum >= minV && offNum <= maxV
    char.note = char.compliant ? '' : `${char.name}: предложено ${char.offered_value}${unit} (требуется ${char.req_value}${unit})`
    return
  }

  const mGte = reqStr.match(/(?:не\s+(?:менее|меньше|ниже)|от|>=|≥)\s*([+-]?\d+(?:\.\d+)?)/i)
  if (mGte) {
    char.compliant = !isNaN(offNum) && offNum >= parseFloat(mGte[1])
    char.note = char.compliant ? '' : `${char.name}: предложено ${char.offered_value}${unit} (требуется ${char.req_value}${unit})`
    return
  }

  const mLte = reqStr.match(/(?:не\s+(?:более|больше|выше)|до|<=|≤)\s*([+-]?\d+(?:\.\d+)?)/i)
  if (mLte) {
    char.compliant = !isNaN(offNum) && offNum <= parseFloat(mLte[1])
    char.note = char.compliant ? '' : `${char.name}: предложено ${char.offered_value}${unit} (требуется ${char.req_value}${unit})`
    return
  }

  if (/^[+-]?\d+(?:\.\d+)?$/.test(reqStr)) {
    char.compliant = !isNaN(offNum) && Math.abs(offNum - parseFloat(reqStr)) <= 1e-6
    char.note = char.compliant ? '' : `${char.name}: предложено ${char.offered_value}${unit} (требуется ${char.req_value}${unit})`
    return
  }

  char.compliant = true
  char.note = ''
}

function onCharValueChange(pos: any, char: any) {
  evaluateCharClient(char)
  const chars = pos.characteristics || []
  const hasChanges = chars.some((c: any) => c.is_changed)
  const rejectedChars = chars.filter((c: any) => c.compliant === false)

  if (rejectedChars.length > 0) {
    pos.is_alternative = true
    pos.compliance_status = 'analog_rejected'
    pos.compliance_note = rejectedChars.map((c: any) => c.note).join('; ')
  } else if (hasChanges) {
    pos.is_alternative = true
    if (pos.compliance_status === 'compliant') {
      pos.compliance_status = 'analog_accepted'
    }
    const diffs = chars.filter((c: any) => c.is_changed).map((c: any) => `${c.name}: ${c.offered_value} ${c.unit || ''}`.trim())
    if (diffs.length > 0 && (!pos.offered_specs || pos.offered_specs === pos.requested_specs)) {
      pos.offered_specs = diffs.join('; ')
    }
  }
  emitPositions()
  emitCompliance()
}

function addCharRow(pos: any) {
  if (!pos.characteristics) pos.characteristics = []
  pos.characteristics.push({ param_idx: pos.characteristics.length + 1, name: 'Параметр', req_value: '', unit: '', offered_value: '', compliant: true, is_changed: false })
  pos._show_chars = true
  emitPositions()
}

function emitPositions() {
  emit('update:positions', localPositions.value)
}

function emitCompliance() {
  const rejected = localPositions.value.filter((p) => p.compliance_status === 'analog_rejected')
  const acceptedAnalogs = localPositions.value.filter((p) => p.compliance_status === 'analog_accepted')
  const tzWarnings = localPositions.value.filter((p) => p.compliance_status === 'tz_warning' || p.has_tz_correction)

  if (rejected.length > 0) {
    const pts = rejected.map((p, idx) => `п. ${p.item_num || idx + 1}`)
    const notes = rejected.map((p, idx) => (p.compliance_note || '').trim() ? `п. ${p.item_num || idx + 1}: ${p.compliance_note.trim()}` : '').filter(Boolean)
    let reason = `Предложены аналоги, которые не соответствуют техническому заданию (${pts.join(', ')})`
    if (notes.length > 0) reason += `. Замечания: ${notes.join('; ')}`
    emit('update:compliance', { admitted: false, rejection_reason: reason, decision_text: `Не соответствует. ${reason}` })
  } else {
    let decisionText = 'Признать соответствующей требованиям закупочной документации.'
    if (acceptedAnalogs.length > 0) {
      const pts = acceptedAnalogs.map((p, idx) => `п. ${p.item_num || idx + 1}`)
      decisionText += ` (предложен эквивалент по ${pts.join(', ')})`
    }
    if (tzWarnings.length > 0) {
      const pts = tzWarnings.map((p, idx) => `п. ${p.item_num || idx + 1}`)
      decisionText += ` (уточнены параметры модели по ${pts.join(', ')})`
    }
    emit('update:compliance', { admitted: true, rejection_reason: '', decision_text: decisionText })
  }
}

function applyTotalToApp() {
  if (positionsTotal.value > 0) emit('apply-price', positionsTotal.value)
}
</script>

<style scoped>
.cursor-pointer { cursor: pointer; }
.select-none { user-select: none; }
.border-top { border-top: 1px solid #e0e0e0; }
.specs-preview { font-size: 11px; max-height: 38px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.text-caption-field :deep(.v-field__input) { font-size: 11.5px !important; padding-top: 4px !important; padding-bottom: 4px !important; min-height: 28px !important; }
.btn-toggle-compact { height: 26px !important; }
.analog-checkbox :deep(.v-label) { font-size: 11px !important; }
</style>
