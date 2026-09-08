<template>
  <!-- ── Add FEO category dialog ── -->
  <v-dialog v-model="addOpen" max-width="520" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-folder-plus-outline" color="primary" class="mr-2" />
        Добавить направление ФЭО
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="addOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-autocomplete
          v-model="feoForm.parentId"
          :items="ctx.feoCategories.value.filter((c: FeoCategory) => c.level < 3)"
          item-title="name" item-value="id"
          label="Родительская категория (необязательно)"
          variant="outlined" density="compact" clearable class="mb-3" hide-details
        />
        <v-text-field v-model="feoForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-row>
          <v-col cols="6">
            <v-text-field v-model="feoForm.code" label="Код" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="feoForm.appendix" label="Приложение" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-textarea
          v-model="feoForm.description"
          label="Пояснение (что входит в направление)"
          variant="outlined" density="compact" rows="2" auto-grow hide-details class="mt-3"
        />
        <v-divider class="my-3" />
        <!-- Блок: По документу ФЭО -->
        <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px" class="mb-3">
          <div class="text-body-2 font-weight-medium mb-3">По документу ФЭО</div>
          <!-- Финансирование по ФЭО -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2">Финансирование по ФЭО</span>
            <v-btn-toggle
              v-model="feoForm.budgetAuto"
              mandatory
              density="compact"
              class="ml-4"
              color="primary"
            >
              <v-btn :value="false" size="x-small">Вручную</v-btn>
              <v-btn :value="true" size="x-small">Авто из детей</v-btn>
            </v-btn-toggle>
          </div>
          <v-text-field
            v-if="!feoForm.budgetAuto"
            v-model.number="feoForm.budget"
            label="Сумма финансирования, ₽"
            variant="outlined" density="compact" type="number" hide-details class="mb-3"
          />
          <!-- Кол-во, ед. изм. и стоимость за ед. по ФЭО -->
          <v-row dense>
            <v-col cols="4">
              <v-text-field
                v-model.number="feoForm.feo_quantity"
                label="Кол-во по ФЭО"
                variant="outlined" density="compact" type="number" hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-combobox
                v-model="feoForm.feo_unit"
                :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
                label="Ед. изм. по ФЭО"
                variant="outlined" density="compact" hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model="feoForm.feo_amount"
                label="Стоимость за ед. по ФЭО"
                variant="outlined" density="compact" type="number" hide-details
                suffix="₽"
              />
            </v-col>
          </v-row>
        </div>
        <!-- Блок: Плановые показатели (CRM) — задача владельца (2026-08-11, Правка 2):
             план вводится именованной плановой позицией внутри категории, а не
             голыми числами на самой категории (planned_quantity/planned_amount) — иначе
             план виден как безымянное число без ответа на вопрос «что именно планируем
             купить». Поля planned_quantity/planned_amount по-прежнему не редактируются
             при создании (см. addFeoCategory) — «Ед. изм.» ниже это единица измерения
             САМОЙ КАТЕГОРИИ (для отображения), а не план.

             План zany-fluttering-mountain.md, п.1/п.5 (2026-08-13): добавлен переключатель
             «Как считать план» — способ теперь ЗАДАЁТСЯ явно, а не угадывается по тому,
             пустые ли поля (это угадывание билось само с собой — см. контекст плана).
             «По плановым позициям» (по умолчанию) — план = Σ позиций категории. «По
             вручную заданной сумме» — ОДНО поле manual_plan_amount, без кол-ва/цены за
             ед. (владелец прямо выбрал одно поле, не количество × цена). -->
        <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px">
          <div class="text-body-2 font-weight-medium mb-1">Как считать план</div>
          <v-btn-toggle
            v-model="feoForm.planSource"
            mandatory
            density="compact"
            color="primary"
            class="mb-2"
          >
            <v-btn value="planned_items" size="x-small">По плановым позициям</v-btn>
            <v-btn value="manual_sum" size="x-small">По вручную заданной сумме</v-btn>
          </v-btn-toggle>
          <div class="text-caption text-medium-emphasis mb-3">
            «По плановым позициям» — план складывается из именованных позиций внутри категории (видно, что именно
            планируем купить). «По вручную заданной сумме» — план это одно число; позиции можно вести отдельно,
            но если их сумма превысит его — потребуется согласование.
          </div>
          <v-text-field
            v-if="feoForm.planSource === 'manual_sum'"
            v-model.number="feoForm.manual_plan_amount"
            label="Плановая сумма, ₽"
            variant="outlined" density="compact" type="number" hide-details class="mb-3"
          />
          <v-alert v-else type="info" variant="tonal" density="compact" class="mb-3 text-caption">
            Создайте категорию и нажмите «Добавить плановую позицию» в панели.
          </v-alert>
          <v-combobox
            v-model="feoForm.unit"
            :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
            label="Ед. изм. категории"
            variant="outlined" density="compact" hide-details
          />
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="addOpen = false">Отмена</v-btn>
        <v-btn color="primary" :loading="savingFeo" :disabled="!feoForm.name || !!feoAddPlanPairError" @click="addFeoCategory">
          Добавить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ── Edit FEO category dialog ── -->
  <v-dialog v-model="editOpen" max-width="520" :fullscreen="mobile">
    <v-card class="dialog-card">
      <v-card-title class="dialog-title">
        <v-icon icon="mdi-pencil-outline" color="primary" class="mr-2" />
        Редактировать направление ФЭО
        <v-btn icon="mdi-close" variant="text" size="small" class="ml-auto" @click="editOpen = false" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-text-field v-model="feoEditForm.name" label="Название *" variant="outlined" density="compact" class="mb-3" hide-details />
        <v-row>
          <v-col cols="6">
            <v-text-field v-model="feoEditForm.code" label="Код" variant="outlined" density="compact" hide-details />
          </v-col>
          <v-col cols="6">
            <v-text-field v-model="feoEditForm.appendix" label="Приложение" variant="outlined" density="compact" hide-details />
          </v-col>
        </v-row>
        <v-autocomplete
          v-model="feoEditForm.parent_id"
          :items="feoParentOptions"
          item-title="name"
          item-value="id"
          label="Родительская категория"
          variant="outlined"
          density="compact"
          clearable
          class="mt-3"
          hint="Очистите для корневого уровня. Или перетащите в таблице."
          persistent-hint
        />
        <v-textarea
          v-model="feoEditForm.description"
          label="Пояснение (что входит в направление)"
          variant="outlined" density="compact" rows="2" auto-grow hide-details class="mt-3"
        />
        <v-divider class="my-3" />
        <!-- Блок: По документу ФЭО -->
        <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px" class="mb-3">
          <div class="text-body-2 font-weight-medium mb-3">По документу ФЭО</div>
          <!-- Финансирование по ФЭО -->
          <div class="d-flex align-center mb-2">
            <span class="text-body-2">Финансирование по ФЭО</span>
            <v-btn-toggle
              v-if="feoEditForm.hasChildren"
              v-model="feoEditForm.budgetAuto"
              mandatory
              density="compact"
              class="ml-4"
              color="primary"
            >
              <v-btn :value="false" size="x-small">Вручную</v-btn>
              <v-btn :value="true" size="x-small">Авто из детей</v-btn>
            </v-btn-toggle>
          </div>
          <v-text-field
            v-if="!feoEditForm.hasChildren || !feoEditForm.budgetAuto"
            v-model.number="feoEditForm.budget"
            label="Сумма финансирования, ₽"
            variant="outlined" density="compact" type="number" hide-details class="mb-2"
          />
          <v-alert
            v-if="feoEditForm.hasChildren && feoEditForm.budgetAuto"
            type="info" variant="tonal" density="compact" class="mb-2 text-caption"
          >
            Сумма рассчитывается автоматически из дочерних направлений
          </v-alert>
          <!-- Кол-во, ед. изм. и стоимость за ед. по ФЭО -->
          <v-row dense>
            <v-col cols="4">
              <v-text-field
                v-model.number="feoEditForm.feo_quantity"
                label="Кол-во по ФЭО"
                variant="outlined" density="compact" type="number" hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-combobox
                v-model="feoEditForm.feo_unit"
                :items="['шт', 'компл', 'кг', 'л', 'м', 'услуга', 'чел.', 'рейс']"
                label="Ед. изм. по ФЭО"
                variant="outlined" density="compact" hide-details
              />
            </v-col>
            <v-col cols="4">
              <v-text-field
                v-model="feoEditForm.feo_amount"
                label="Стоимость за ед. по ФЭО"
                variant="outlined" density="compact" type="number" hide-details
                suffix="₽"
              />
            </v-col>
          </v-row>
        </div>
        <!-- Блок: Как считать план — план zany-fluttering-mountain.md, п.1/п.5
             (2026-08-13). Способ теперь ЗАДАЁТСЯ явно переключателем, а не угадывается
             по тому, пустые ли поля planned_quantity/planned_amount (угадывание билось
             само с собой — см. контекст плана, категория 3710). «По вручную заданной
             сумме» — ОДНО поле manual_plan_amount (не количество × цена — владелец
             прямо выбрал одно поле). Переключение на «ручную сумму» у категории, где
             уже есть плановые позиции (feoEditPlanSourceSwitchWarning), сопровождается
             предупреждением о последствиях: позиции останутся, но план будет считаться
             от суммы, их превышение потребует согласования. -->
        <div style="border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:8px;padding:12px" class="mb-3">
          <div class="text-body-2 font-weight-medium mb-1">Как считать план</div>
          <v-btn-toggle
            v-model="feoEditForm.planSource"
            mandatory
            density="compact"
            color="primary"
            class="mb-2"
          >
            <v-btn value="planned_items" size="x-small">По плановым позициям</v-btn>
            <v-btn value="manual_sum" size="x-small">По вручную заданной сумме</v-btn>
          </v-btn-toggle>
          <div class="text-caption text-medium-emphasis mb-3">
            «По плановым позициям» — план складывается из именованных позиций внутри категории (видно, что именно
            планируем купить). «По вручную заданной сумме» — план это одно число; позиции можно вести отдельно,
            но если их сумма превысит его — потребуется согласование.
          </div>

          <v-alert
            v-if="feoEditPlanSourceSwitchWarning"
            type="warning" variant="tonal" density="compact" class="mb-3 text-caption"
          >
            У категории уже есть плановые позиции — они останутся на месте, но план будет считаться от введённой
            суммы. Если сумма позиций превысит её, потребуется согласование превышения.
          </v-alert>

          <template v-if="feoEditForm.planSource === 'manual_sum'">
            <v-text-field
              v-model.number="feoEditForm.manual_plan_amount"
              label="Плановая сумма, ₽"
              variant="outlined" density="compact" type="number" hide-details
            />
          </template>

          <!-- Правка 2Б (2026-08-11): три состояния старого способа отображения плана —
               (1) есть подкатегории — план считают они; (2) план не задан — подсказка
               завести плановую позицию; (3) план задан старыми полями категории — только
               для чтения + перенос в плановую позицию (openConvertManualPlanToItem). Всё
               показывается только в режиме «по плановым позициям» — режим «по сумме» выше
               уже закрыл вопрос одним полем. -->
          <template v-else>
            <v-alert
              v-if="feoEditForm.hasChildren"
              type="info" variant="tonal" density="compact" class="text-caption"
            >
              У категории есть подкатегории: план считается по ним, собственный план категории в расчёте не участвует.
            </v-alert>

            <template v-else-if="feoEditManualPlanSet">
              <div class="d-flex align-center flex-wrap mb-2" style="gap:8px">
                <span class="text-body-2">
                  Плановое количество: <strong>{{ feoEditForm.planned_quantity ?? '—' }} {{ feoEditForm.unit || 'ед.' }}</strong>
                </span>
                <v-chip size="x-small" color="orange" variant="tonal">старый формат</v-chip>
              </div>
              <div class="text-body-2 mb-2">
                Плановая цена за единицу: <strong>{{ feoEditForm.planned_amount != null ? formatCurrency(feoEditForm.planned_amount) : '—' }}</strong>
              </div>
              <div class="text-body-2 mb-3">
                Плановая сумма: {{ feoEditForm.planned_quantity ?? '—' }} × {{ feoEditForm.planned_amount != null ? formatCurrency(feoEditForm.planned_amount) : '—' }}
                <template v-if="feoEditForm.planned_quantity != null && feoEditForm.planned_amount != null">
                  = <strong>{{ formatCurrency(Number(feoEditForm.planned_quantity) * Number(feoEditForm.planned_amount)) }}</strong>
                </template>
              </div>
              <v-alert
                v-if="feoEditPlanPairError"
                type="warning" variant="tonal" density="compact" class="mb-3 text-caption"
              >
                {{ feoEditPlanPairError }}
              </v-alert>
              <div class="text-caption text-medium-emphasis mb-3">
                План записан полями самой категории, без названия. Перенесите его в плановую позицию — тогда будет
                видно, что именно запланировано, и позицию можно будет править.
              </div>
              <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-swap-horizontal" @click="convertCategoryEditPlanToItem">
                Перенести в плановую позицию
              </v-btn>
            </template>

            <template v-else>
              <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
                План задаётся плановой позицией внутри категории: нажмите «Добавить плановую позицию» ниже. Так у
                плана будет название (что именно планируем купить), а не просто число.
              </v-alert>
              <v-btn size="small" variant="tonal" color="teal" prepend-icon="mdi-playlist-plus" @click="openAddPlannedItemFromCategoryEdit">
                Добавить плановую позицию
              </v-btn>
            </template>
          </template>
        </div>
        <v-checkbox v-model="feoEditForm.is_active" label="Активна" density="compact" hide-details class="mt-2" />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="editOpen = false">Отмена</v-btn>
        <!-- feoEditPlanPairError НЕ гейтит кнопку (см. ответ в отчёте по Правке 2Б):
             planned_quantity/planned_amount больше не редактируются в этом диалоге,
             мисматч пары может быть только унаследован из БД — категория с таким
             мисматчем обязана сохраняться (иначе «Сохранить» блокируется навсегда
             без способа это поправить из этой формы). Предупреждение всё равно
             показывается пользователю в блоке «старый формат» выше. -->
        <v-btn color="primary" :loading="savingFeo" :disabled="!feoEditForm.name" @click="updateFeoCategory">
          Сохранить
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { useToast, type ToastType } from '@/composables/useToast'
import { numOrNull } from '@/utils/numberFormat'
import { formatCurrency } from '@/composables/subsidies/format'
import { collectSubtreeIds } from '@/composables/subsidies/feoCategoryUtils'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import type { FeoCategory, FeoNode } from '@/composables/subsidies/types'

const addOpen = defineModel<boolean>('addOpen', { default: false })
const editOpen = defineModel<boolean>('editOpen', { default: false })

const emit = defineEmits<{ (e: 'saved'): void }>()

const { mobile } = useDisplay()
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success', opts?: { actionText?: string; onAction?: () => void; duration?: number }) {
  toast.addToast(text, color, opts)
}

const ctx = useSubsidyDetailCtx()

const savingFeo = ref(false)

const feoForm = ref({ parentId: null as number | null, name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, planned_quantity: null as number | null, qtyAuto: false, planned_amount: null as number | null, amtAuto: false, unit: '' as string, feo_quantity: null as number | null, feo_unit: '' as string, description: '', feo_amount: '' as string | number, planSource: 'planned_items' as 'planned_items' | 'manual_sum', manual_plan_amount: null as number | null })
const feoEditForm = ref({ name: '', code: '', appendix: '', budget: null as number | null, budgetAuto: false, planned_quantity: null as number | null, qtyAuto: false, planned_amount: null as number | null, amtAuto: false, unit: '' as string, is_active: true, hasChildren: false, parent_id: null as number | null, feo_quantity: null as number | null, feo_unit: '' as string, description: '', feo_amount: '' as string | number, planSource: 'planned_items' as 'planned_items' | 'manual_sum', manual_plan_amount: null as number | null })

const feoEditTarget = ref<FeoCategory | null>(null)

// Правило владельца (2026-08-09): «Плановое кол-во»/«Плановая стоимость за ед.» —
// пара. Задана цена без количества (или наоборот) → сумма НЕ считается автоматически
// и молча ломается (см. backend _validate_plan_pair в feo_categories.py, тот же порог
// >0). auto-режим («Авто из детей», отправляется как null) считается пустым полем —
// зеркалит то, что реально уйдёт в payload PUT/POST.
function feoPlanPairError(
  qty: number | null, qtyAuto: boolean,
  amt: number | null, amtAuto: boolean,
): string {
  const qFilled = !qtyAuto && qty != null && Number(qty) > 0
  const aFilled = !amtAuto && amt != null && Number(amt) > 0
  if (qFilled === aFilled) return ''
  return qFilled
    ? 'Задано количество, но не задана цена за ед. — заполните оба поля (сумма посчитается автоматически), либо очистите количество и задайте план общей суммой отдельной плановой позицией («Добавить плановую» в панели) без указания количества.'
    : 'Задана цена за ед., но не задано количество — заполните оба поля (сумма посчитается автоматически), либо очистите цену и задайте план общей суммой отдельной плановой позицией («Добавить плановую» в панели) без указания количества.'
}

const feoAddPlanPairError = computed(() => feoPlanPairError(
  feoForm.value.planned_quantity, feoForm.value.qtyAuto,
  feoForm.value.planned_amount, feoForm.value.amtAuto,
))
const feoEditPlanPairError = computed(() => feoPlanPairError(
  feoEditForm.value.planned_quantity, feoEditForm.value.qtyAuto,
  feoEditForm.value.planned_amount, feoEditForm.value.amtAuto,
))

// Правка 2Б (2026-08-11): категория без детей и без ручного плана листа (ни одного
// хотя бы с одним из двух полей — тот самый «старый формат»; ноль/пусто в обоих —
// план ещё не задан вовсе.
const feoEditManualPlanSet = computed(() => {
  const f = feoEditForm.value
  if (f.hasChildren) return false
  const q = f.planned_quantity
  const a = f.planned_amount
  return (q != null && Number(q) > 0) || (a != null && Number(a) > 0)
})

// План zany-fluttering-mountain.md, п.1: «при переключении на ручную сумму у
// категории, где уже есть плановые позиции, — предупреждение о последствиях»
// (владелец: позиции останутся, план будет считаться от суммы, их превышение
// потребует согласования). «Уже есть позиции» — категория до открытия диалога
// была в режиме 'planned_items' (feoEditTarget — исходный, не мутируется формой)
// и её Σ позиций (plan_manual из planTreeByCat) больше нуля.
const feoEditPlanSourceSwitchWarning = computed(() => {
  const target = feoEditTarget.value
  if (!target) return false
  const origSource = target.plan_source || 'planned_items'
  if (origSource !== 'planned_items') return false
  if (feoEditForm.value.planSource !== 'manual_sum') return false
  return ctx.getFeoPlanManual(target.id) > 0.005
})

const feoParentOptions = computed(() => {
  if (!feoEditTarget.value) return []
  const excludeIds = new Set(collectSubtreeIds(ctx.feoCategories.value, feoEditTarget.value.id))
  return ctx.feoCategories.value
    .filter((c: FeoCategory) => !excludeIds.has(c.id))
    .map((c: FeoCategory) => ({ id: c.id, name: '  '.repeat(c.level - 1) + c.name }))
})

function openAdd(parentId: number | null) {
  feoForm.value.parentId = parentId
  addOpen.value = true
}

function openEdit(node: FeoNode) {
  feoEditTarget.value = node
  const autoMode = node.hasChildren && node.budget === null
  const qtyAutoMode = node.hasChildren && node.planned_quantity === null
  const amtAutoMode = node.hasChildren && node.planned_amount === null
  feoEditForm.value = {
    name: node.name,
    code: node.code || '',
    appendix: node.appendix || '',
    budget: node.budget ?? null,
    budgetAuto: autoMode,
    planned_quantity: node.planned_quantity ?? null,
    qtyAuto: qtyAutoMode,
    planned_amount: node.planned_amount ?? null,
    amtAuto: amtAutoMode,
    unit: node.unit || '',
    is_active: node.is_active,
    hasChildren: node.hasChildren,
    parent_id: node.parent_id ?? null,
    feo_quantity: node.feo_quantity ?? null,
    feo_unit: node.feo_unit || '',
    description: node.description || '',
    feo_amount: node.feo_amount ?? '',
    planSource: node.plan_source || 'planned_items',
    manual_plan_amount: node.manual_plan_amount ?? null,
  }
  editOpen.value = true
}

// Правка 2Б (2026-08-11): из диалога редактирования категории — план не задан вовсе →
// сразу открыть форму «Добавить плановую позицию» на той же категории (переиспользует
// openAddPlannedItem в родителе, второй диалог не заводим).
function openAddPlannedItemFromCategoryEdit() {
  if (!feoEditTarget.value) return
  const categoryId = feoEditTarget.value.id
  editOpen.value = false
  ctx.openAddPlannedItem(categoryId)
}

// Правка 2Б: план уже задан старым способом (planned_quantity/planned_amount на самой
// категории) → перенести его в именованную плановую позицию тем же путём, что и кнопка
// в панели. Функции нужен FeoNode (с hasChildren/depth), а feoEditTarget — просто
// FeoCategory, поэтому берём актуальный узел из дерева по id.
function convertCategoryEditPlanToItem() {
  if (!feoEditTarget.value) return
  const node = ctx.flattenAll(ctx.feoTree.value).find((n: FeoNode) => n.id === feoEditTarget.value!.id)
  if (!node) return
  editOpen.value = false
  ctx.openConvertManualPlanToItem(node)
}

async function addFeoCategory() {
  if (!ctx.selectedSubsidy.value) return
  if (feoAddPlanPairError.value) { showSnack(feoAddPlanPairError.value, 'error'); return }
  savingFeo.value = true
  try {
    const res = await apiFetch<FeoCategory>('/feo-categories/', {
      method: 'POST',
      body: JSON.stringify({
        subsidy_id: ctx.selectedSubsidy.value.id,
        parent_id: feoForm.value.parentId || null,
        name: feoForm.value.name,
        code: feoForm.value.code || null,
        appendix: feoForm.value.appendix || null,
        is_active: true,
        // budget/planned_quantity/planned_amount/feo_quantity/feo_amount/manual_plan_amount —
        // numOrNull (2026-09-04): '' → null, 0 сохраняется как число.
        budget: feoForm.value.budgetAuto ? null : numOrNull(feoForm.value.budget),
        planned_quantity: feoForm.value.qtyAuto ? null : numOrNull(feoForm.value.planned_quantity),
        planned_amount: feoForm.value.amtAuto ? null : numOrNull(feoForm.value.planned_amount),
        unit: feoForm.value.unit || null,
        feo_quantity: numOrNull(feoForm.value.feo_quantity),
        feo_unit: feoForm.value.feo_unit || null,
        description: feoForm.value.description?.trim() || null,
        feo_amount: numOrNull(feoForm.value.feo_amount),
        // План zany-fluttering-mountain.md, п.1: способ расчёта плана — при 'manual_sum'
        // уходит введённая сумма, при 'planned_items' поле обнуляется (истина в позициях).
        plan_source: feoForm.value.planSource,
        manual_plan_amount: feoForm.value.planSource === 'manual_sum' ? numOrNull(feoForm.value.manual_plan_amount) : null,
      })
    })
    ctx.feoCategories.value.push(res)
    addOpen.value = false
    feoForm.value = { parentId: null, name: '', code: '', appendix: '', budget: null, budgetAuto: false, planned_quantity: null, qtyAuto: false, planned_amount: null, amtAuto: false, unit: '', feo_quantity: null, feo_unit: '', description: '', feo_amount: '', planSource: 'planned_items', manual_plan_amount: null }
    showSnack('Направление добавлено')
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
    ctx.syncFeoFilled()
    emit('saved')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка добавления направления', 'error')
  } finally {
    savingFeo.value = false
  }
}

async function updateFeoCategory() {
  if (!feoEditTarget.value) return
  // feoEditPlanPairError больше НЕ блокирует сохранение здесь (см. комментарий у кнопки
  // «Сохранить» в шаблоне) — planned_quantity/planned_amount не редактируются в этом
  // диалоге, мисматч пары может прийти только унаследованным из БД, и сохранение
  // остальных полей категории (название, код и т.д.) обязано проходить в любом случае.
  savingFeo.value = true
  try {
    // Если parent_id изменился — вызываем move endpoint
    const oldParentId = feoEditTarget.value.parent_id ?? null
    const newParentId = feoEditForm.value.parent_id ?? null
    if (oldParentId !== newParentId) {
      const moveRes = await apiFetch<any>(`/feo-categories/${feoEditTarget.value.id}/move`, {
        method: 'PATCH', body: JSON.stringify({ parent_id: newParentId }),
      })
      if (moveRes?.warning) showSnack(moveRes.warning, 'warning')
    }
    // Обновляем остальные поля
    await apiFetch<FeoCategory>(`/feo-categories/${feoEditTarget.value.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        subsidy_id: feoEditTarget.value.subsidy_id,
        parent_id: newParentId,
        name: feoEditForm.value.name,
        code: feoEditForm.value.code || null,
        appendix: feoEditForm.value.appendix || null,
        is_active: feoEditForm.value.is_active,
        budget: feoEditForm.value.budgetAuto ? null : numOrNull(feoEditForm.value.budget),
        planned_quantity: feoEditForm.value.qtyAuto ? null : numOrNull(feoEditForm.value.planned_quantity),
        planned_amount: feoEditForm.value.amtAuto ? null : numOrNull(feoEditForm.value.planned_amount),
        unit: feoEditForm.value.unit || null,
        feo_quantity: numOrNull(feoEditForm.value.feo_quantity),
        feo_unit: feoEditForm.value.feo_unit || null,
        description: feoEditForm.value.description?.trim() || null,
        feo_amount: numOrNull(feoEditForm.value.feo_amount),
        // План zany-fluttering-mountain.md, п.1: способ расчёта плана — см. комментарий
        // у того же поля в addFeoCategory выше.
        plan_source: feoEditForm.value.planSource,
        manual_plan_amount: feoEditForm.value.planSource === 'manual_sum' ? numOrNull(feoEditForm.value.manual_plan_amount) : null,
      })
    })
    editOpen.value = false
    showSnack('Направление обновлено')
    if (ctx.selectedId.value) await ctx.loadFeo(ctx.selectedId.value)
    ctx.syncFeoFilled()
    emit('saved')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.detail || e?.message || 'Ошибка обновления', 'error')
  } finally {
    savingFeo.value = false
  }
}

defineExpose({ openAdd, openEdit })
</script>

<style scoped>
/* .dialog-card/.dialog-title — было в <style scoped> SubsidiesView.vue, пока
   диалог был её частью; вынесено вместе с диалогом (волна 5c) — иначе scoped CSS
   другого файла эти классы не достаёт (проверено на ContractorEditDialog.vue —
   тот же паттерн: каждый диалог держит эти два правила у себя). */
.dialog-card {}
.dialog-title {
  display: flex; align-items: center;
  font-size: 16px !important; font-weight: 600 !important;
  padding: 16px 20px !important;
}
</style>
