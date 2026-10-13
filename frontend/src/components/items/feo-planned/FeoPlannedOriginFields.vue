<template>
  <!-- ── Происхождение плановой позиции: «По ФЭО» / «Внутренний план» ──
       Общая секция-компонент (владелец, п.15б, 13.10.2026): раньше в обоих
       диалогах («Добавить плановую позицию» и «Редактировать плановую
       позицию») этот блок был почти буквальной копией — вынесен в один
       компонент (Правило №6), чтобы раскладка не разъезжалась между ними.

       Раскладка по требованию владельца: каждая галочка раскрывает СВОИ поля
       количество/ед.изм./цена/сумма, вместо одного общего набора цифр над
       обеими галочками. Модель данных НЕ меняется — у FeoPlannedItem есть
       ровно ОДИН основной комплект чисел (quantity/unit/unit_price/amount,
       «внутренний план» — единственный источник дерева/контроля превышения,
       см. backend/app/models/feo_planned_item.py) и ОДИН необязательный
       второй комплект «по ФЭО» (feo_quantity/feo_unit_price/feo_amount),
       который раньше показывался лишь когда ОБЕ галочки стояли разом.

       Поэтому поля показываются так:
       - «Внутренний план» отмечена → показывает ОСНОВНОЙ комплект (это и
         есть «внутренний план» в модели) — как и раньше.
       - «По ФЭО» отмечена И «Внутренний план» ТОЖЕ отмечена → показывает
         ВТОРОЙ, feo_*-комплект (раньше показывался тем же условием, здесь
         просто переехал под свою галочку).
       - «По ФЭО» отмечена, а «Внутренний план» — НЕТ → второго комплекта нет
         смысла заводить (вся позиция — чисто по ФЭО), «По ФЭО» показывает тот
         же ОСНОВНОЙ комплект (он и есть единственное число позиции).
       - Обе галочки сняты → основной комплект показан без подписи
         происхождения (легаси/обычная позиция, как было раньше) — ничего не
         прячем, чтобы не потерять ввод количества/суммы у таких позиций. -->
  <div class="text-caption text-medium-emphasis mb-1">Происхождение позиции</div>
  <v-checkbox v-model="form.is_feo_breakdown" density="compact" hide-details class="mb-1">
    <template #label>
      <div>
        <div style="line-height:1.2">По ФЭО</div>
        <div class="text-caption text-medium-emphasis" style="line-height:1.2">жёсткая разбивка ФЭО — покупать будут именно это, отчётность строгая</div>
      </div>
    </template>
  </v-checkbox>
  <!-- Предупреждение при снятии «По ФЭО», когда обе галочки стояли разом —
       снятие в этот момент убирает у позиции отдельный ФЭО-комплект чисел
       (feo_quantity/feo_unit_price/feo_amount), хотя там могли быть введены
       числа (владелец: «снятие галочки = данные этого источника очищаются...
       с понятным предупреждением, если там были числа»). Остальные случаи
       (внутренний план не отмечен, или обе сняты) не теряют данных — основной
       комплект остаётся на месте, предупреждать не о чём. -->
  <div v-if="feoClearWarning" class="text-caption text-warning mb-2" style="line-height:1.3">
    <v-icon icon="mdi-alert-outline" size="13" style="margin-top:-2px" class="mr-1" />Числа «по ФЭО» (кол-во/цена/сумма) очищены — отметьте галочку снова, если понадобятся
  </div>
  <template v-if="form.is_feo_breakdown">
    <div class="pl-4 mb-2" style="border-left:2px solid #DCFCE7">
      <template v-if="form.is_internal_plan">
        <!-- Обе галочки разом — свой, отдельный комплект «по ФЭО» (для сверки
             с внутренним планом ниже). Ед. изм. не дублируется — физическая
             единица одна на позицию, показана у «Внутреннего плана». -->
        <div class="text-caption text-medium-emphasis mb-1">Числа по ФЭО</div>
        <v-row v-if="form.payment_mode !== 'monthly'" dense>
          <v-col cols="5">
            <v-text-field v-model.number="form.feoQuantity" label="Кол-во по ФЭО" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="7">
            <v-text-field v-model.number="form.feoUnitPrice" label="Цена за единицу по ФЭО, ₽" type="number" variant="outlined" density="compact" suffix="₽" />
          </v-col>
        </v-row>
        <v-text-field
          v-if="form.payment_mode !== 'monthly'"
          v-model="form.feoAmount"
          label="Сумма по ФЭО, ₽" type="number"
          variant="outlined" density="compact"
          :readonly="feoAmountIsComputed"
          :bg-color="feoAmountIsComputed ? 'grey-lighten-4' : undefined"
          :hint="feoAmountIsComputed ? 'Считается автоматически: кол-во × цена за единицу по ФЭО' : 'Необязательно — не заполняйте, если числа по ФЭО и по внутреннему плану совпадают'"
          persistent-hint
          class="mb-1"
        />
      </template>
      <template v-else>
        <!-- Только «По ФЭО» — это и есть единственный комплект чисел позиции. -->
        <v-row v-if="form.payment_mode !== 'monthly'" dense>
          <v-col cols="5">
            <v-text-field v-model="form.quantity" label="Кол-во" type="number" variant="outlined" density="compact" />
          </v-col>
          <v-col cols="7">
            <v-text-field v-model="form.unit" label="Ед. изм." variant="outlined" density="compact" placeholder="шт, кг, услуга..." />
          </v-col>
        </v-row>
        <v-text-field
          v-if="form.payment_mode !== 'monthly'"
          v-model.number="form.unitPrice"
          type="number" label="Цена за единицу, ₽ (необязательно)"
          variant="outlined" density="compact" class="mb-1"
          :hint="form.unitPrice === '' || form.unitPrice == null ? unitPriceNotFixedHint : ''"
          :persistent-hint="form.unitPrice === '' || form.unitPrice == null"
        />
        <v-text-field
          v-model="form.amount"
          label="Сумма, ₽" type="number"
          variant="outlined" density="compact"
          :readonly="amountIsComputed"
          :bg-color="amountIsComputed ? 'grey-lighten-4' : undefined"
          :class="form.payment_mode === 'monthly' ? 'd-none' : 'mb-1'"
        />
        <div v-if="form.payment_mode !== 'monthly'" class="text-caption text-medium-emphasis mb-1" style="line-height:1.35">
          <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ priceCaption }}
        </div>
      </template>
    </div>
  </template>

  <v-checkbox v-model="form.is_internal_plan" density="compact" hide-details class="mb-1">
    <template #label>
      <div>
        <div style="line-height:1.2">Внутренний план</div>
        <div class="text-caption text-medium-emphasis" style="line-height:1.2">в ФЭО была более широкая категория (или позиции не было) — разбивку придумали сами</div>
      </div>
    </template>
  </v-checkbox>
  <template v-if="form.is_internal_plan">
    <div class="pl-4 mb-2" style="border-left:2px solid #FEF3C7">
      <v-row v-if="form.payment_mode !== 'monthly'" dense>
        <v-col cols="5">
          <v-text-field v-model="form.quantity" label="Кол-во" type="number" variant="outlined" density="compact" />
        </v-col>
        <v-col cols="7">
          <v-text-field v-model="form.unit" label="Ед. изм." variant="outlined" density="compact" placeholder="шт, кг, услуга..." />
        </v-col>
      </v-row>
      <v-text-field
        v-if="form.payment_mode !== 'monthly'"
        v-model.number="form.unitPrice"
        type="number" label="Цена за единицу, ₽ (необязательно)"
        variant="outlined" density="compact" class="mb-1"
        :hint="form.unitPrice === '' || form.unitPrice == null ? unitPriceNotFixedHint : ''"
        :persistent-hint="form.unitPrice === '' || form.unitPrice == null"
      />
      <v-text-field
        v-model="form.amount"
        label="Сумма, ₽" type="number"
        variant="outlined" density="compact"
        :readonly="amountIsComputed"
        :bg-color="amountIsComputed ? 'grey-lighten-4' : undefined"
        :class="form.payment_mode === 'monthly' ? 'd-none' : 'mb-1'"
      />
      <div v-if="form.payment_mode !== 'monthly'" class="text-caption text-medium-emphasis mb-1" style="line-height:1.35">
        <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ priceCaption }}
      </div>
    </div>
  </template>

  <!-- Ни одна галочка не стоит — легаси/обычная позиция без деления на
       происхождение: показываем единственный (основной) комплект чисел без
       подписи, как это выглядело до появления галочек «По ФЭО»/«Внутренний
       план» — иначе ввести количество/сумму такой позиции стало бы негде. -->
  <template v-if="!form.is_feo_breakdown && !form.is_internal_plan">
    <v-row v-if="form.payment_mode !== 'monthly'" dense>
      <v-col cols="5">
        <v-text-field v-model="form.quantity" label="Кол-во" type="number" variant="outlined" density="compact" />
      </v-col>
      <v-col cols="7">
        <v-text-field v-model="form.unit" label="Ед. изм." variant="outlined" density="compact" placeholder="шт, кг, услуга..." />
      </v-col>
    </v-row>
    <v-text-field
      v-if="form.payment_mode !== 'monthly'"
      v-model.number="form.unitPrice"
      type="number" label="Цена за единицу, ₽ (необязательно)"
      variant="outlined" density="compact" class="mb-1"
      :hint="form.unitPrice === '' || form.unitPrice == null ? unitPriceNotFixedHint : ''"
      :persistent-hint="form.unitPrice === '' || form.unitPrice == null"
    />
    <v-text-field
      v-model="form.amount"
      label="Сумма, ₽" type="number"
      variant="outlined" density="compact"
      :readonly="amountIsComputed"
      :bg-color="amountIsComputed ? 'grey-lighten-4' : undefined"
      :class="form.payment_mode === 'monthly' ? 'd-none' : 'mb-3'"
    />
    <div v-if="form.payment_mode !== 'monthly'" class="text-caption text-medium-emphasis mb-2" style="line-height:1.35">
      <v-icon icon="mdi-information-outline" size="13" style="margin-top:-2px" class="mr-1" />{{ priceCaption }}
    </div>
  </template>
</template>

<script setup lang="ts">
// Общая секция «Происхождение позиции» — PlannedItemAddDialog.vue и
// PlannedItemEditDialog.vue передают СВОЙ реактивный объект формы (у обоих
// composables, useFeoPlannedItemAddDialog.ts/useFeoPlannedItemEditDialog.ts,
// совпадающие по именам поля — quantity/unit/unitPrice/amount/
// is_feo_breakdown/is_internal_plan/feoQuantity/feoUnitPrice/feoAmount/
// payment_mode) — компонент мутирует их напрямую через v-model (объект
// передан по ссылке, это тот же приём, что и ctx-объекты в остальной
// панели ФЭО, Правило №6 — второй копии разметки не заводим).
import { ref, watch } from 'vue'
import { useToast } from '@/composables/useToast'
import { UNIT_PRICE_NOT_FIXED_HINT } from '@/constants/planPriceLabels'

interface OriginForm {
  quantity: string | number | null
  unit: string
  unitPrice: string | number | null
  amount: string | number | null
  is_feo_breakdown: boolean
  is_internal_plan: boolean
  feoQuantity: string | number | null
  feoUnitPrice: string | number | null
  feoAmount: string | number | null
  payment_mode: 'one_time' | 'monthly'
}

const props = defineProps<{
  form: OriginForm
  amountIsComputed: boolean
  priceCaption: string
  feoAmountIsComputed: boolean
}>()

const unitPriceNotFixedHint = UNIT_PRICE_NOT_FIXED_HINT
const toast = useToast()
const feoClearWarning = ref(false)

// Снятие «По ФЭО» при стоящей разом «Внутренний план» — у позиции исчезает
// ЕДИНСТВЕННОЕ место для feo_quantity/feo_unit_price/feo_amount (поле «Числа
// по ФЭО» показывается только в этом сочетании галочек, см. шаблон выше).
// Если там были введены числа — очищаем их сразу (а не только на сохранении:
// отдельного «черновика» у диалогов нет) и один раз показываем предупреждение
// (владелец, п.15б). Остальные переключения галочек НИЧЕГО не теряют —
// основной комплект (quantity/unitPrice/amount) остаётся как есть при любом
// сочетании, предупреждать не о чём.
watch(
  () => props.form.is_feo_breakdown,
  (val, oldVal) => {
    if (!(oldVal && !val)) return
    if (!props.form.is_internal_plan) return // второго комплекта и не было
    const hasData = props.form.feoQuantity !== '' && props.form.feoQuantity != null
      || props.form.feoUnitPrice !== '' && props.form.feoUnitPrice != null
      || props.form.feoAmount !== '' && props.form.feoAmount != null
    if (!hasData) return
    props.form.feoQuantity = ''
    props.form.feoUnitPrice = ''
    props.form.feoAmount = ''
    feoClearWarning.value = true
    toast.info('Числа «по ФЭО» очищены')
  },
)
</script>
