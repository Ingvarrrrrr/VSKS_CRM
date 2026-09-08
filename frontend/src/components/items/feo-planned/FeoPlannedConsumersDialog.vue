<template>
  <!-- «Кто расходует план» (владелец, 2026-08-20) — расшифровка GET
       /feo-planned-items/{id}/consumers, см. useFeoPlannedConsumers.ts. -->
  <v-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" max-width="760">
    <v-card>
      <v-card-title class="text-subtitle-1">
        Кто расходует план{{ row ? ' — «' + row.name + '»' : '' }}
      </v-card-title>
      <v-card-text>
        <div v-if="loading" class="d-flex justify-center align-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <v-alert v-else-if="error" type="error" variant="tonal" density="compact">
          {{ error }}
        </v-alert>
        <template v-else-if="data && row">
          <!-- Итог — ТЕ ЖЕ слагаемые, что строка списка (consumedFor/residualFor row),
               НЕ пересчитаны заново: серверные data.consumed/residual не знают о позициях
               ЭТОЙ формы, ещё не сохранённых на сервер (см. dialogPendingItems ниже) —
               если взять их напрямую, число в диалоге разойдётся с числом в строке
               (жалоба владельца, боевой случай: строка «выбрано 11 281», диалог «съедено
               0 ₽»). -->
          <div class="text-body-2 mb-3">
            план {{ fmt(row.planned_amount) }} ·
            выбрано {{ fmt(consumedFor(row)) }} ·
            <span :class="planResidualDisplay(row).cssClass">
              {{ planResidualDisplay(row).text }}
            </span>
          </div>
          <div v-if="dialogIsEmpty" class="text-body-2 text-medium-emphasis">
            На эту плановую позицию ничего не привязано — план ещё свободен целиком.
          </div>
          <template v-else>
            <!-- Группа 1: позиции ЭТОЙ ЖЕ открытой формы — причина, по которой «выбрано»
                 в строке больше нуля даже когда сервер ещё ничего не видит (форма не
                 сохранена). -->
            <div v-if="dialogPendingItems.length" class="feo-consumers-group mb-3">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-1">{{ dialogFormLabel }}</div>
              <v-table density="compact" class="feo-consumers-table">
                <thead>
                  <tr><th>Что</th><th class="text-right">Кол-во</th><th class="text-right">Сумма</th></tr>
                </thead>
                <tbody>
                  <tr v-for="(p, i) in dialogPendingItems" :key="'pend-' + i">
                    <td>{{ p.name }}</td>
                    <td class="text-right">{{ fmtNum(p.quantity) }} {{ p.unit || '' }}</td>
                    <td class="text-right">{{ fmt(p.amount) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>

            <!-- Группа 2: позиции ДРУГИХ закупок, реально расходующие план (то, что
                 сервер считает в consumed) — своя (purchaseId) отфильтрована,
                 она уже показана группой 1. -->
            <div v-if="dialogOtherPurchases.length" class="feo-consumers-group mb-3">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-1">Другие закупки, расходующие план</div>
              <v-table density="compact" class="feo-consumers-table">
                <thead>
                  <tr>
                    <th>Что</th><th>Где</th><th>Статус</th>
                    <th class="text-right">Кол-во</th><th class="text-right">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(c, i) in dialogOtherPurchases"
                    :key="'pur-' + i"
                    :class="{ 'feo-consumer-row--excluded': !c.counts_towards_consumed }"
                  >
                    <td>{{ c.item_name }}</td>
                    <td>
                      <a href="#" class="feo-consumer-link" @click.prevent="$emit('go-to-purchase', c.purchase_id)">
                        Закупка {{ c.registry_number || ('№' + (c.purchase_number ?? c.purchase_id)) }}
                      </a>
                      <div class="text-caption text-medium-emphasis">{{ c.purchase_subject }}</div>
                      <div v-if="c.wish_id" class="text-caption text-medium-emphasis">из заявки №{{ c.wish_id }}</div>
                    </td>
                    <td>
                      {{ c.status_label }}
                      <div v-if="!c.counts_towards_consumed" class="text-caption text-medium-emphasis">
                        не входит в остаток
                      </div>
                    </td>
                    <td class="text-right">{{ fmtNum(c.quantity) }} {{ c.unit || '' }}</td>
                    <td class="text-right">{{ fmt(c.amount) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>

            <!-- Группа 3: позиции ДРУГИХ заявок — план НЕ резервируют (резервируют
                 только после переноса в план закупок), на остаток не влияют. Своя
                 заявка (wishId) отфильтрована — она уже показана группой 1. -->
            <div v-if="dialogOtherWishes.length" class="feo-consumers-group">
              <div class="text-caption font-weight-medium text-medium-emphasis mb-1">
                Другие заявки — план не резервируют, на остаток не влияют (заявка резервирует
                план только после переноса в план закупок)
              </div>
              <v-table density="compact" class="feo-consumers-table">
                <thead>
                  <tr>
                    <th>Что</th><th>Заявка</th><th>Статус</th>
                    <th class="text-right">Кол-во</th><th class="text-right">Сумма</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(c, i) in dialogOtherWishes" :key="'wish-' + i" class="feo-consumer-row--excluded">
                    <td>{{ c.item_name }}</td>
                    <td>
                      <div>Заявка №{{ c.wish_id }} «{{ c.wish_title }}»</div>
                      <div class="text-caption text-medium-emphasis">автор: {{ c.author_name || '—' }}</div>
                    </td>
                    <td>
                      {{ c.status_label }}
                      <div class="text-caption text-medium-emphasis">не входит в остаток</div>
                    </td>
                    <td class="text-right">{{ fmtNum(c.quantity) }} {{ c.unit || '' }}</td>
                    <td class="text-right">{{ fmt(c.amount) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </div>
          </template>
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import type { FeoPlannedConsumer, FeoPlannedConsumersResponse } from '@/composables/items/feoPlanned/useFeoPlannedConsumers'
import type { PendingItemEntry } from '@/composables/items/feoPlanned/useFeoPlannedRows'
import type { PlanResidualDisplay } from '@/utils/numberFormat'

defineProps<{
  modelValue: boolean
  loading: boolean
  error: string | null
  row: FeoPlanPosition | null
  data: FeoPlannedConsumersResponse | null
  dialogPendingItems: PendingItemEntry[]
  dialogOtherPurchases: FeoPlannedConsumer[]
  dialogOtherWishes: FeoPlannedConsumer[]
  dialogIsEmpty: boolean
  dialogFormLabel: string
  fmt: (v: number | null | undefined) => string
  fmtNum: (v: number | null | undefined) => string
  consumedFor: (row: FeoPlanPosition) => number
  planResidualDisplay: (row: FeoPlanPosition) => PlanResidualDisplay
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  'go-to-purchase': [id: number | undefined]
}>()
</script>
