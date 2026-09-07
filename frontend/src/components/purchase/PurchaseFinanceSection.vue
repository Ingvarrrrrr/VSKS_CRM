<template>
  <!-- 3. Финансы (скрыто для employee и manager) -->
  <v-card v-if="isSectionVisible('financial_indicators') || isSectionVisible('contract_type')" variant="outlined" class="mb-4">
    <v-card-title v-if="isSectionVisible('financial_indicators')" class="text-subtitle-1 font-weight-bold px-4 pt-4">Финансовые показатели</v-card-title>
    <v-card-text>
      <v-row v-if="isSectionVisible('financial_indicators')">
        <v-col cols="12" md="3">
          <div id="pub-target-nmck" style="position:relative">
          <div v-if="pointerTarget === 'nmck'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
          <div :class="pointerTarget === 'nmck' ? 'pub-glow' : ''">
          <div class="text-caption text-medium-emphasis mb-1">НМЦД (итого)</div>
          <v-btn-toggle v-model="nmckMode" mandatory density="compact" color="primary" class="mb-2" style="width:100%">
            <v-btn value="auto" size="small" style="flex:1;text-transform:none;letter-spacing:0">Авто</v-btn>
            <v-btn value="manual" size="small" style="flex:1;text-transform:none;letter-spacing:0">Вручную</v-btn>
          </v-btn-toggle>
          <v-text-field v-if="nmckMode === 'auto'"
            :model-value="formatMoney(displayNmck)"
            label="НМЦД (итого)" variant="outlined" density="compact"
            readonly bg-color="grey-lighten-4"
            :hint="nmckHint" persistent-hint />
          <v-text-field v-else
            v-model.number="nmckManualValue"
            label="НМЦД (итого, вручную)" variant="outlined" density="compact"
            type="number" suffix="₽"
            hint="Введено вручную. Цена за единицу в ТЗ скрыта." persistent-hint
            @update:model-value="calcEconomy" />
          </div><!-- /pub-glow -->
          </div><!-- /pub-target-nmck -->
        </v-col>
        <v-col cols="12" md="3">
          <div class="text-caption text-medium-emphasis mb-1">Цена договора</div>
          <v-btn-toggle v-if="!isFrameworkCumulative" v-model="contractPriceMode" mandatory density="compact" color="primary" class="mb-2" style="width:100%">
            <v-btn value="auto" size="small" style="flex:1;text-transform:none;letter-spacing:0">Авто</v-btn>
            <v-btn value="manual" size="small" style="flex:1;text-transform:none;letter-spacing:0">Вручную</v-btn>
          </v-btn-toggle>
          <!-- Рамочный накопительный: показываем сумму заказов -->
          <v-text-field v-if="isFrameworkCumulative && selectedFrameworkContract"
            :model-value="selectedFrameworkContract.total_ordered ? formatMoney(Number(selectedFrameworkContract.total_ordered)) : ''"
            label="Сумма заказов по договору" variant="outlined"
            density="compact" suffix="₽" readonly bg-color="grey-lighten-4"
            :placeholder="!selectedFrameworkContract.total_ordered ? 'Ещё ничего не заказывали' : ''"
            :hint="selectedFrameworkContract.total_ordered ? 'Сумма всех заказов по рамочному договору' : ''"
            persistent-hint persistent-placeholder />
          <!-- Остальные типы: стандартное поле цены -->
          <v-text-field v-else v-model.number="form.contract_price"
            :label="isFramework ? 'Предельная сумма договора' : 'Цена договора'" variant="outlined"
            density="compact" type="number" suffix="₽"
            :readonly="contractPriceMode === 'auto' || (isFramework && !!selectedFrameworkContract)"
            :bg-color="(contractPriceMode === 'auto' || (isFramework && !!selectedFrameworkContract)) ? 'grey-lighten-4' : undefined"
            :hint="isFramework && selectedFrameworkContract ? 'Подтянуто из рамочного договора' : contractPriceMode === 'manual' ? 'Введено вручную' : contractPriceHint"
            persistent-hint
            :color="nmckWarningLevel === 'error' ? 'error' : nmckWarningLevel === 'warning' ? 'warning' : undefined"
            @update:model-value="calcEconomy">
            <template v-slot:append-inner>
              <v-icon v-if="nmckWarningLevel === 'error'" icon="mdi-alert" color="error" size="18" :title="`Превышение НМЦД на ${nmckExcessPct}%`" />
              <v-icon v-else-if="nmckWarningLevel === 'warning'" icon="mdi-alert-outline" color="warning" size="18" :title="`Близко к НМЦД (+${nmckExcessPct}%)`" />
            </template>
          </v-text-field>
          <div v-if="nmckWarningLevel" class="text-caption mt-n2 mb-1"
            :class="nmckWarningLevel === 'error' ? 'text-error' : 'text-warning'">
            {{ nmckWarningLevel === 'error' ? `Превышение НМЦД на ${nmckExcessPct}%` : `Близко к НМЦД (+${nmckExcessPct}%)` }}
          </div>
        </v-col>
        <v-col cols="12" md="3" class="pt-8">
          <!-- framework_cumulative без лимита: нет отрицательного остатка, только счётчик -->
          <template v-if="isFrameworkCumulative && selectedFrameworkContract && selectedFrameworkContract.remaining_ordered == null">
            <div class="text-caption text-medium-emphasis mb-1">Накопленная сумма заказов</div>
            <div class="text-body-2 font-weight-bold">{{ formatMoney(Number(selectedFrameworkContract.total_ordered ?? 0)) }} ₽</div>
            <div class="text-caption text-medium-emphasis">Накопительный договор без предельной суммы</div>
            <!-- TODO(phase26): кнопка «Согласовать у руководителя» если сумма выходит за разумный предел -->
          </template>
          <!-- framework_with_amount или cumulative с лимитом: показываем остаток -->
          <v-text-field v-else-if="isFramework && selectedFrameworkContract"
            :model-value="selectedFrameworkContract.remaining_ordered != null ? formatMoney(selectedFrameworkContract.remaining_ordered) : '—'"
            :label="isFrameworkCumulative ? 'Остаток (лимит − накоплено)' : 'Остаток средств на договоре'" variant="outlined"
            density="compact" suffix="₽" readonly
            :bg-color="(selectedFrameworkContract.remaining_ordered ?? 0) < 0 ? 'red-lighten-5' : 'grey-lighten-4'"
            :hint="(selectedFrameworkContract.remaining_ordered ?? 0) < 0 ? 'Превышен лимит договора' : 'Предельная сумма минус сумма заказанного'" persistent-hint />
          <v-text-field v-else :model-value="form.economy ?? ''" label="Экономия (авто)" variant="outlined"
            density="compact" suffix="₽" readonly bg-color="grey-lighten-4"
            hint="НМЦД минус Цена договора. Считается автоматически." persistent-hint />
        </v-col>
        <v-col cols="12" md="3" class="pt-8">
          <v-text-field v-model.number="form.price_increase" label="Удорожание (доп. соглашения)"
            variant="outlined" density="compact" type="number" suffix="₽"
            hint="Указывается при увеличении цены по доп. соглашению к договору" persistent-hint />
        </v-col>
      </v-row>
      <!-- Тип договора перенесён в Основную информацию -->
      <v-row v-if="false" class="mt-0">
        <v-col><!-- placeholder --></v-col>
        <v-col v-if="false" cols="12">
          <v-table density="compact" class="framework-siblings-table mt-1">
            <thead>
              <tr>
                <th style="width:50px">№</th>
                <th>Наименование</th>
                <th>Статус</th>
                <th class="text-right">НМЦД</th>
                <th class="text-right">Цена договора</th>
                <th class="text-right">Оплачено</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="s in frameworkSiblings" :key="s.id"
                :class="s.id === purchaseId ? 'framework-sibling-current' : ''"
                style="cursor:pointer"
                @click="s.id !== purchaseId && $router.push(`/orders/${s.id}`)"
              >
                <td>
                  <v-chip :color="s.id === purchaseId ? 'primary' : 'default'" size="x-small" variant="tonal">
                    {{ s.framework_seq ?? '—' }}
                  </v-chip>
                </td>
                <td class="text-caption">{{ s.item_name || s.subject || '—' }}</td>
                <td><v-chip :color="statusColor(s.status)" size="x-small" variant="tonal">{{ statusLabel(s.status) }}</v-chip></td>
                <td class="text-right text-caption">{{ s.total_nmck ? formatMoney(Number(s.total_nmck)) : '—' }}</td>
                <td class="text-right text-caption">{{ s.contract_price ? formatMoney(Number(s.contract_price)) : '—' }}</td>
                <td class="text-right text-caption">{{ s.payment_amount ? formatMoney(Number(s.payment_amount)) : '—' }}</td>
              </tr>
              <!-- Итоговая строка -->
              <tr class="framework-total-row">
                <td colspan="3" class="text-caption font-weight-bold">Итого по договору</td>
                <td class="text-right text-caption font-weight-bold">{{ formatMoney(frameworkTotals.nmck) }}</td>
                <td class="text-right text-caption font-weight-bold">{{ formatMoney(frameworkTotals.price) }}</td>
                <td class="text-right text-caption font-weight-bold">{{ formatMoney(frameworkTotals.paid) }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-col>
      </v-row>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
// Блок «Финансовые показатели» (НМЦД / цена договора / экономия / удорожание).
// Вынесено из CreateOrderView.vue (рефакторинг без изменения поведения,
// часть 3). form — reactive-объект родителя (мутируется напрямую v-model, как
// и раньше). nmckMode/nmckManualValue/contractPriceMode — refs из
// composables/purchase/usePurchaseNmck.ts, композабл вызывается ОДИН раз в
// родителе (ПРАВИЛО №6) — сюда приходят через v-model/defineModel, чтобы
// запись из этого компонента отражалась в том же состоянии родителя.
// calcEconomy пишет в form и остаётся во view (используется в save()).
//
// Внутри есть блок `v-if="false"` («сиблинги по рамочному договору») —
// это уже неактивный (недостижимый) код в исходном файле, перенесён
// байт-в-байт без изменений вместе с остальным шаблоном секции; statusColor/
// statusLabel там — тот же пред-существующий дефект (необъявленные
// идентификаторы, см. STATUS_COLOR/STATUS_LABEL в другом месте кода),
// не исправляется в рамках этого рефакторинга.
defineProps<{
  form: any
  isFramework: boolean
  isFrameworkCumulative: boolean
  selectedFrameworkContract: any
  displayNmck: number
  nmckHint: string
  contractPriceHint: string
  nmckWarningLevel: 'error' | 'warning' | null
  nmckExcessPct: number
  formatMoney: (v: number) => string
  calcEconomy: () => void
  pointerTarget: string | null
  isSectionVisible: (key: string) => boolean
  frameworkSiblings: any[]
  frameworkTotals: { nmck: number; price: number; paid: number }
  purchaseId: number | null
}>()

const nmckMode = defineModel<'auto' | 'manual'>('nmckMode', { required: true })
const nmckManualValue = defineModel<number | null>('nmckManualValue', { required: true })
const contractPriceMode = defineModel<'auto' | 'manual'>('contractPriceMode', { required: true })
</script>
