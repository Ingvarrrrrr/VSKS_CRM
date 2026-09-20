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
}>()

// Сентинелы: 0% — валидная облагаемая ставка и не может делить одно значение
// null/undefined с «не облагается» (vat_applicable=false) или с «ещё не
// знаю» (vat_applicable=null) — три РАЗНЫХ состояния нужны три РАЗНЫХ ключа.
const EXEMPT = 'exempt'
const UNKNOWN = 'unknown'

const rateOptions = [
  { title: 'Ещё не знаю', value: UNKNOWN },
  { title: 'Не облагается', value: EXEMPT },
  { title: '0%', value: 0 },
  { title: '5%', value: 5 },
  { title: '7%', value: 7 },
  { title: '10%', value: 10 },
  { title: '20%', value: 20 },
  { title: '22%', value: 22 },
]

const selectedRate = computed<string | number>(() => {
  if (props.vatApplicable === null) return UNKNOWN
  return props.vatApplicable ? (props.vatRate ?? 22) : EXEMPT
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
