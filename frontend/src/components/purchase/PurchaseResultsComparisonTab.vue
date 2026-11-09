<template>
  <div class="comparison-tab">
    <!-- Баннер предупреждения об уточнениях ТЗ -->
    <v-alert
      v-if="hasTzCorrection"
      type="warning"
      variant="tonal"
      density="compact"
      icon="mdi-alert-circle-outline"
      class="mb-3 text-caption font-weight-medium"
      closable
    >
      <strong>Внимание комиссии:</strong> В предложениях участников обнаружены уточнения характеристик модели Заказчика (возможно, неточность или опечатка в техническом задании). Проверьте строки, выделенные оранжевым цветом!
    </v-alert>

    <!-- Верхняя панель: кнопка выгрузки Excel и легенда -->
    <div class="d-flex flex-wrap align-center justify-space-between gap-2 mb-3">
      <div class="d-flex flex-wrap align-center gap-2">
        <v-btn
          color="deep-purple"
          variant="flat"
          size="small"
          prepend-icon="mdi-file-excel-box"
          :disabled="!applications.length || !publicationId"
          :href="exportUrl"
          target="_blank"
        >
          Скачать сводную таблицу (Excel)
        </v-btn>
        <span class="text-caption text-medium-emphasis">
          Сравнение требований ТЗ и ТКП {{ applications.length }} участников
        </span>
      </div>

      <!-- Легенда статусов -->
      <div class="d-flex flex-wrap align-center gap-1 text-caption">
        <v-chip size="x-small" color="success" variant="flat">✓ Соответствует ТЗ</v-chip>
        <v-chip size="x-small" color="orange-darken-2" variant="flat">⚠️ Уточнение ТЗ</v-chip>
        <v-chip size="x-small" color="info" variant="flat">✓ Эквивалент (аналог)</v-chip>
        <v-chip size="x-small" color="error" variant="flat">✗ Не соответствует</v-chip>
      </div>
    </div>

    <!-- Пустое состояние -->
    <div v-if="!applications.length" class="text-center py-8 text-medium-emphasis">
      <v-icon icon="mdi-table-pivot" size="48" class="mb-2 text-grey-lighten-1" />
      <div>Нет данных для формирования сводной таблицы</div>
      <div class="text-caption mt-1">Добавьте заявки или загрузите протокол и ТКП участников</div>
    </div>

    <!-- Таблица сравнения -->
    <div v-else class="comparison-table-wrapper rounded border">
      <table class="comparison-table text-caption">
        <thead>
          <tr class="bg-grey-lighten-4">
            <th rowspan="2" class="col-num">№</th>
            <th rowspan="2" class="col-name">Наименование и характеристики по ТЗ</th>
            <th rowspan="2" class="col-unit">Ед.</th>
            <th rowspan="2" class="col-qty">Кол-во / Требование ТЗ</th>
            <th
              v-for="(app, aIdx) in applications"
              :key="'app-hdr-' + aIdx"
              colspan="2"
              class="col-app-hdr text-center border-left"
              :class="{'bg-amber-lighten-5': app.place === 1}"
            >
              <div class="font-weight-bold">
                {{ app.supplier_short_name || app.supplier_name || `Участник №${aIdx + 1}` }}
                <v-chip v-if="app.place === 1" size="x-small" color="amber-darken-3" variant="flat" class="ml-1">
                  1 место 🏆
                </v-chip>
              </div>
              <div class="text-caption text-medium-emphasis">
                {{ app.admitted ? 'Допущен' : 'Отклонён' }} • {{ formatMoney(app.price_with_vat) }} ₽
              </div>
            </th>
          </tr>
          <tr class="bg-grey-lighten-4 border-subhdr">
            <template v-for="(app, aIdx) in applications" :key="'app-subhdr-' + aIdx">
              <th class="border-left subhdr-model">Предложенная модель</th>
              <th class="subhdr-price">Цена / Статус</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <template v-for="(pos, pIdx) in basePositions" :key="'pos-' + pIdx">
            <!-- Основная строка товара -->
            <tr class="row-item-main">
              <td class="font-weight-bold text-center bg-grey-lighten-5">{{ pos.item_num || (pIdx + 1) }}</td>
              <td class="font-weight-bold">
                {{ pos.requested_name || `Товар №${pIdx + 1}` }}
              </td>
              <td class="text-center text-medium-emphasis">{{ pos.unit || 'шт' }}</td>
              <td class="text-center font-weight-medium">{{ pos.quantity || 1 }}</td>

              <!-- Данные каждого участника по товару -->
              <template v-for="(app, aIdx) in applications" :key="'app-pos-' + aIdx + '-' + pIdx">
                <td class="border-left" :class="getPosCellClass(getAppPos(app, pIdx))">
                  <div class="font-weight-medium">{{ getAppPos(app, pIdx)?.offered_name || 'По ТЗ' }}</div>
                  <div class="text-caption">
                    <v-chip
                      size="x-small"
                      :color="getOfferTypeColor(getAppPos(app, pIdx))"
                      variant="tonal"
                      class="mt-1"
                    >
                      {{ getOfferTypeLabel(getAppPos(app, pIdx)) }}
                    </v-chip>
                  </div>
                </td>
                <td :class="getPosCellClass(getAppPos(app, pIdx))">
                  <div class="font-weight-bold">{{ formatMoney(getAppPos(app, pIdx)?.total_price) }} ₽</div>
                  <div class="text-caption text-medium-emphasis">{{ getAppPos(app, pIdx)?.vat_rate || app.vat_label || 'Без НДС' }}</div>
                  <v-chip
                    size="x-small"
                    :color="getComplianceColor(getAppPos(app, pIdx))"
                    variant="flat"
                    class="mt-1"
                  >
                    {{ getComplianceLabel(getAppPos(app, pIdx)) }}
                  </v-chip>
                </td>
              </template>
            </tr>

            <!-- Подстроки структурированных характеристик -->
            <tr
              v-for="(ch, cIdx) in (pos.characteristics || [])"
              :key="'char-' + pIdx + '-' + cIdx"
              class="row-char-sub"
            >
              <td class="text-center text-medium-emphasis">{{ (pos.item_num || (pIdx + 1)) + '.' + (cIdx + 1) }}</td>
              <td class="pl-4 text-grey-darken-3">
                <v-icon icon="mdi-menu-right" size="14" class="text-grey mr-1" />
                {{ ch.name }}
              </td>
              <td class="text-center text-grey">{{ ch.unit || '' }}</td>
              <td class="text-center text-grey-darken-2">{{ ch.req_value }}</td>

              <!-- Значение характеристики у каждого участника -->
              <template v-for="(app, aIdx) in applications" :key="'app-char-' + aIdx + '-' + pIdx + '-' + cIdx">
                <td
                  colspan="2"
                  class="border-left char-val-cell"
                  :class="getCharCellClass(getAppChar(app, pIdx, cIdx))"
                >
                  <div class="d-flex align-center justify-space-between">
                    <span class="font-weight-medium">
                      {{ getAppChar(app, pIdx, cIdx)?.offered_value || ch.req_value }}
                      <span v-if="ch.unit" class="text-grey">{{ ch.unit }}</span>
                    </span>
                    <v-icon
                      :icon="getCharIcon(getAppChar(app, pIdx, cIdx))"
                      :color="getCharIconColor(getAppChar(app, pIdx, cIdx))"
                      size="16"
                    />
                  </div>
                  <div
                    v-if="getAppChar(app, pIdx, cIdx)?.tz_corrected_by_supplier"
                    class="text-orange-darken-3 font-weight-bold"
                    style="font-size: 10px;"
                  >
                    ⚠️ Уточнено участником (возможно, опечатка в ТЗ)
                  </div>
                </td>
              </template>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatMoney } from '@/utils/formatMoney'

const props = defineProps<{
  results: any
  publicationId: number | string | null
}>()

const applications = computed<Array<any>>(() => props.results?.applications || [])

const basePositions = computed<Array<any>>(() => {
  for (const app of applications.value) {
    if (app.positions && app.positions.length) return app.positions
  }
  return []
})

const exportUrl = computed(() => `/api/publications/${props.publicationId}/results/comparison.xlsx`)

const hasTzCorrection = computed(() => {
  return applications.value.some((app: any) =>
    (app.positions || []).some((p: any) =>
      p.compliance_status === 'tz_warning' ||
      p.has_tz_correction ||
      (p.characteristics || []).some((c: any) => c.tz_corrected_by_supplier)
    )
  )
})

function getAppPos(app: any, pIdx: number) {
  return app.positions?.[pIdx] || null
}

function getAppChar(app: any, pIdx: number, cIdx: number) {
  const pos = getAppPos(app, pIdx)
  return pos?.characteristics?.[cIdx] || null
}

function getOfferTypeLabel(pos: any) {
  if (!pos) return '—'
  if (pos.is_exact_model_offer) return 'Модель по ТЗ'
  if (pos.is_alternative) return 'Эквивалент (аналог)'
  return 'По ТЗ'
}

function getOfferTypeColor(pos: any) {
  if (!pos) return 'grey'
  if (pos.is_exact_model_offer) return 'success'
  if (pos.is_alternative) return 'info'
  return 'grey'
}

function getComplianceLabel(pos: any) {
  if (!pos) return '—'
  if (pos.compliance_status === 'tz_warning' || pos.has_tz_correction) return 'Уточнение ТЗ'
  if (pos.compliance_status === 'analog_rejected') return 'Отклонён'
  if (pos.compliance_status === 'analog_accepted') return 'Аналог принят'
  return 'Соответствует'
}

function getComplianceColor(pos: any) {
  if (!pos) return 'grey'
  if (pos.compliance_status === 'tz_warning' || pos.has_tz_correction) return 'orange-darken-2'
  if (pos.compliance_status === 'analog_rejected') return 'error'
  if (pos.compliance_status === 'analog_accepted') return 'info'
  return 'success'
}

function getPosCellClass(pos: any) {
  if (!pos) return ''
  if (pos.compliance_status === 'tz_warning' || pos.has_tz_correction) return 'bg-orange-lighten-5'
  if (pos.compliance_status === 'analog_rejected') return 'bg-red-lighten-5'
  if (pos.compliance_status === 'analog_accepted') return 'bg-blue-lighten-5'
  return ''
}

function getCharCellClass(char: any) {
  if (!char) return ''
  if (char.tz_corrected_by_supplier) return 'bg-orange-lighten-5'
  if (char.compliant === false) return 'bg-red-lighten-5'
  if (char.is_changed) return 'bg-blue-lighten-5'
  return ''
}

function getCharIcon(char: any) {
  if (!char) return 'mdi-check'
  if (char.tz_corrected_by_supplier) return 'mdi-alert'
  if (char.compliant === false) return 'mdi-close'
  return 'mdi-check'
}

function getCharIconColor(char: any) {
  if (!char) return 'grey'
  if (char.tz_corrected_by_supplier) return 'orange-darken-2'
  if (char.compliant === false) return 'error'
  if (char.is_changed) return 'info'
  return 'success'
}
</script>

<style scoped>
.comparison-table-wrapper {
  overflow-x: auto;
  max-width: 100%;
}
.comparison-table {
  width: 100%;
  border-collapse: collapse;
}
.comparison-table th, .comparison-table td {
  border: 1px solid #e0e0e0;
  padding: 6px 8px;
  vertical-align: middle;
}
.col-num { width: 36px; }
.col-name { min-width: 220px; }
.col-unit { width: 44px; }
.col-qty { width: 110px; }
.col-app-hdr { min-width: 200px; }
.border-left { border-left: 2px solid #bdbdbd !important; }
.row-item-main {
  background-color: #fbfbfb;
  border-top: 2px solid #9e9e9e;
}
.row-char-sub {
  background-color: #ffffff;
  font-size: 11px;
}
.subhdr-model { min-width: 130px; }
.subhdr-price { min-width: 100px; }
.char-val-cell {
  padding: 4px 8px;
}
</style>
