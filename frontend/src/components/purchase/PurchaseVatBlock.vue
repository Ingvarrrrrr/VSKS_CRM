<template>
  <!-- Единый блок НДС (владелец, закупка РЕЕ-2026-00918, 2026-09-16): «НДС должно
       быть в ОДНОМ месте, в панели "Позиции закупки", переключатели там должны
       что-то давать». Раньше режим (одинаковый/для каждой позиции) переключался
       здесь, а сама ставка/статья НК РФ вводились совсем в другом месте —
       секция «Параметры договора» (PurchaseContractParamsSection.vue), которую
       владелец не нашёл. Теперь оба переключателя и сама ставка — один блок,
       единственный источник — props.vatApplicable/vatRate/vatExemptionArticle/
       vatMode (мутируются ТОЛЬКО через emit наверх, копий состояния нет,
       ПРАВИЛО №6). Якорь id="pub-target-vat" — цель стрелки-гида (guideArrowTo). -->
  <div id="pub-target-vat" style="position:relative">
    <div v-if="pointerTarget === 'vat'" class="pub-pointer"><span class="mdi mdi-arrow-down-bold" /></div>
    <div :class="pointerTarget === 'vat' ? 'pub-glow' : ''" class="pa-1">
      <div class="d-flex ga-2 mb-1 align-center flex-wrap">
        <span class="text-caption text-medium-emphasis">НДС:</span>
        <v-btn-toggle
          :model-value="vatMode || 'uniform'"
          density="compact" rounded="lg" color="primary" border mandatory
          :class="{ 'mobile-toggle-wrap': mobile }"
          @update:model-value="(v: string) => emit('update:vatMode', v)"
        >
          <v-btn value="uniform" size="x-small">Одинаковый на всю закупку</v-btn>
          <v-btn value="per_item" size="x-small">Для каждой позиции</v-btn>
        </v-btn-toggle>

        <template v-if="(vatMode || 'uniform') === 'uniform'">
          <v-select
            :model-value="selectedRate"
            :items="rateOptions"
            density="compact" variant="outlined" hide-details
            style="max-width:190px;min-width:160px"
            label="Ставка НДС"
            @update:model-value="onRateSelect"
          />
          <v-text-field
            v-if="vatApplicable === false"
            :model-value="vatExemptionArticle"
            :label="vatExemptionAutoBasis
              ? 'Статья НК РФ (основание определено автоматически)'
              : (requireArticle ? 'Статья НК РФ *' : 'Статья НК РФ')"
            variant="outlined" density="compact"
            :placeholder="vatExemptionAutoBasis ? '' : 'напр. п.2 ст.346.11 НК РФ (УСН)'"
            :rules="(!requireArticle || vatExemptionAutoBasis) ? [] : [(v: string) => !!(v && v.trim()) || 'Без основания документы с НДС не сформируются']"
            :hint="vatExemptionAutoBasis
              ? `Основание найдено автоматически: ${vatExemptionAutoBasis}. Можно ввести своё — оно заменит автоматическое.`
              : (requireArticle
                ? 'Обязательно для печати документов: без статьи НК РФ система откажет в формировании договора/приказа/листа согласования. Не требуется для самозанятых исполнителей и договоров ГПХ с физлицом — там основание определяется само.'
                : 'На этапе заявки не обязательно — понадобится перед формированием договора, когда определится подрядчик. Можно заполнить сейчас или позже.')"
            persistent-hint
            style="min-width:280px;flex:1 1 320px"
            @update:model-value="(v: string) => emit('update:vatExemptionArticle', v)"
          />
          <span v-if="vatApplicable === null" class="text-caption text-medium-emphasis">
            Уточните, когда определится подрядчик
          </span>
        </template>
        <span v-else class="text-caption text-medium-emphasis">
          Ставка выбирается в строке каждой позиции ниже
        </span>
      </div>

      <!-- 2026-10-02 (.planning/quick/2026-10-02-vat-on-top/PLAN.md): два отдельных
           переключателя «НДС в цене / сверху» — один для цены ТЗ (каталог/КП), один
           для цены договора (договор/УПД). Выбор на всю закупку; в режиме per_item
           это фолбэк для строк без своего флага (useVatCalc.ts::effectiveVatOnTop). -->
      <div class="d-flex ga-4 mt-1 flex-wrap">
        <div>
          <v-btn-toggle
            :model-value="tzVatOnTop ? 'on_top' : 'included'"
            density="compact" rounded="lg" color="primary" border mandatory
            :class="{ 'mobile-toggle-wrap': mobile }"
            @update:model-value="(v: string) => emit('update:tzVatOnTop', v === 'on_top')"
          >
            <v-btn value="included" size="x-small">Цена ТЗ: с НДС</v-btn>
            <v-btn value="on_top" size="x-small">без НДС, НДС сверху</v-btn>
          </v-btn-toggle>
          <div class="text-caption text-medium-emphasis mt-1" style="max-width:280px">
            <template v-if="!tzVatOnTop">Цена ТЗ уже с НДС — сумма строки не меняется.</template>
            <template v-else-if="tzRateKnown">Сумма строки будет с НДС: цена × кол-во + {{ tzRatePercent }}%.</template>
            <template v-else>Ставка не указана — НДС не добавлен.</template>
          </div>
        </div>
        <div v-if="showContractToggle !== false">
          <v-btn-toggle
            :model-value="contractVatOnTop ? 'on_top' : 'included'"
            density="compact" rounded="lg" color="primary" border mandatory
            :class="{ 'mobile-toggle-wrap': mobile }"
            @update:model-value="(v: string) => emit('update:contractVatOnTop', v === 'on_top')"
          >
            <v-btn value="included" size="x-small">Цена договора: с НДС</v-btn>
            <v-btn value="on_top" size="x-small">без НДС, НДС сверху</v-btn>
          </v-btn-toggle>
          <div class="text-caption text-medium-emphasis mt-1" style="max-width:280px">
            <template v-if="!contractVatOnTop">Цена договора уже с НДС — сумма строки не меняется.</template>
            <template v-else-if="tzRateKnown">Сумма строки будет с НДС: цена × кол-во + {{ tzRatePercent }}%.</template>
            <template v-else>Ставка не указана — НДС не добавлен.</template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Единственный источник значений — form.vat_applicable/vat_rate/vat_exemption_article/
// vat_mode родителя (CreateOrderView.vue), сюда доходят как typed props/emits через
// PurchaseItemsEditor.vue (тот же паттерн, что уже был у vatMode/update:vatMode) —
// НЕ через целиком проброшенный `form` (как у PurchaseContractParamsSection.vue),
// чтобы не завести два способа достучаться до одних и тех же полей.
import { computed } from 'vue'
// ПРАВИЛО №6: список процентных ставок — ОДИН источник (useVatCalc.ts), тот же,
// что у построчных таблиц позиций (ItemsTableFlat/ItemsTableStages/ItemsCardsView/
// ItemsTableWish). Раньше здесь была своя копия [0,5,7,10,20,22] — сама ставок
// не путала, но по Правилу №6 обязана переиспользовать, не дублировать.
import { VAT_RATE_OPTIONS } from '@/composables/useVatCalc'

const props = defineProps<{
  mobile: boolean
  vatMode: 'uniform' | 'per_item'
  // Владелец (2026-09-17): «ещё раз введи возможность поставить "Ставка НДС"
  // поле "Ещё не знаю"» — третье состояние, отдельное от «Не облагается»:
  // null = решение не принято (обычно потому что подрядчик ещё не выбран),
  // false = точно определено, что НДС не начисляется. purchases.vat_applicable
  // в БД и так nullable — раньше фронт просто нигде не давал выбрать null явно.
  vatApplicable: boolean | null
  vatRate: number | null
  vatExemptionArticle: string | null
  vatExemptionAutoBasis: string | null
  // 2026-10-02: заголовочные флаги закупки «цена введена без НДС, добавить сверху»
  // — отдельно для цены ТЗ и цены договора (решение владельца, см. PLAN.md). Источник
  // — purchases.tz_vat_on_top/contract_vat_on_top, мутируются только через emit.
  tzVatOnTop?: boolean
  contractVatOnTop?: boolean
  // На этапе заявки договора ещё нет — скрываем переключатель цены договора
  // (владелец: «выбор отдельный для цены ТЗ и для цены договора», но договора
  // у заявки просто не существует). true по умолчанию — обычная закупка.
  showContractToggle?: boolean
  pointerTarget?: string | null
  // Владелец (2026-09-17): на этапе заявки подрядчик и, соответственно, реальное
  // основание освобождения от НДС ещё не известны — блокировать заявку из-за
  // пустой статьи НК РФ нельзя. Обязательно это поле только на этапе закупки/
  // договора (requireArticle=true, значение по умолчанию — старое поведение).
  // Единственный источник решения «нужна ли статья прямо сейчас» —
  // PurchaseItemsEditor::props.isWishStage, сюда приходит уже готовым.
  requireArticle?: boolean
}>()

const requireArticle = computed(() => props.requireArticle !== false)

const emit = defineEmits<{
  'update:vatMode': [mode: string]
  'update:vatApplicable': [value: boolean | null]
  'update:vatRate': [value: number | null]
  'update:vatExemptionArticle': [value: string | null]
  'update:tzVatOnTop': [value: boolean]
  'update:contractVatOnTop': [value: boolean]
}>()

// 2026-10-02: подсказка под переключателями «сверху» — ставка известна только
// когда vatApplicable===true и vatRate задан (в uniform-режиме; per_item ставку
// решает строка). «Не облагается»/«ещё не знаю» намеренно НЕ добавляют НДС —
// effectiveVatOnTop/lineTotalWithVat в useVatCalc.ts читают ставку=0 так же.
const tzRateKnown = computed(() => props.vatApplicable === true && props.vatRate != null)
const tzRatePercent = computed(() => props.vatRate ?? '')

// Сентинелы: 0% — валидная облагаемая ставка и не может делить одно значение
// null/undefined с «не облагается» (vat_applicable=false), с «ещё не знаю»
// (vat_applicable=null) или с «ставка не указана» (vat_applicable=true,
// vat_rate=null) — четыре РАЗНЫХ состояния, четыре РАЗНЫХ ключа.
const EXEMPT = 'exempt'
const UNKNOWN = 'unknown'
// Владелец (26.09, закупка PEE-2026-00957): «с чего ты поставил 22%?» — раньше
// vat_applicable=true + vat_rate=null (закупка из плана/заявки, где ставка ещё
// не известна) отображались как выбранная ставка 22% (`vatRate ?? 22`) —
// ВЫДУМАННЫЙ фолбэк поверх отсутствующего значения. Теперь это отдельное
// состояние с собственным пунктом списка, ничего не подставляем.
const RATE_UNSET = 'rate_unset'

// Процентные пункты — из общего useVatCalc.VAT_RATE_OPTIONS (Правило №6, та же
// ставка НДС, что и в построчных таблицах позиций), но без её null-пункта
// («Не облагается» там означает то же самое, что EXEMPT здесь — не дублируем
// пункт, просто не берём null из общего списка и добавляем сентинелы блока
// поверх процентных значений.
const rateOptions = [
  { title: 'Ещё не знаю', value: UNKNOWN },
  { title: 'Не облагается', value: EXEMPT },
  { title: 'Ставка не указана', value: RATE_UNSET },
  ...VAT_RATE_OPTIONS
    .filter(o => o.value !== null)
    .map(o => ({ title: o.title, value: Number(String(o.value).replace('%', '')) })),
]

const selectedRate = computed<string | number>(() => {
  if (props.vatApplicable === null) return UNKNOWN
  if (props.vatApplicable === false) return EXEMPT
  // vatApplicable === true
  return props.vatRate ?? RATE_UNSET
})

function onRateSelect(v: string | number) {
  if (v === UNKNOWN) {
    emit('update:vatApplicable', null)
    emit('update:vatRate', null)
    return
  }
  if (v === EXEMPT) {
    emit('update:vatApplicable', false)
    return
  }
  if (v === RATE_UNSET) {
    emit('update:vatApplicable', true)
    emit('update:vatRate', null)
    return
  }
  emit('update:vatApplicable', true)
  emit('update:vatRate', Number(v))
}
</script>

<style scoped>
/* Тот же мобильный фикс, что и у group-тумблеров в PurchaseItemsEditor.vue
   (см. комментарий там) — растягивает v-btn-toggle на всю ширину на мобильном,
   чтобы длинный текст «ОДИНАКОВЫЙ НА ВСЮ ЗАКУПКУ» не обрезался за краем диалога. */
.mobile-toggle-wrap {
  width: 100%;
}
.mobile-toggle-wrap :deep(.v-btn) {
  flex: 1 1 0;
  height: auto !important;
  min-height: 32px;
  padding-top: 4px;
  padding-bottom: 4px;
}
.mobile-toggle-wrap :deep(.v-btn__content) {
  white-space: normal;
  text-align: center;
  line-height: 1.2;
}
</style>
