<template>
  <!-- Выбор ПЛАНОВОЙ ПОЗИЦИИ (единый источник /feo-categories/plan-positions —
       конечный элемент дерева ФЭО с планом, статья ФЭО с планом, или детализация
       Ур.5 FeoPlannedItem) — визуально продолжение дерева ФЭО (FeoTreeSelect): те же
       рельсы/локти (feoTreeRails.css), корневая строка — выбранная категория, ниже —
       её плановые позиции (сама категория + дочерние конечные элементы).
       Оркестратор (рефакторинг монолита 1527 → ~300 строк, 2026-09-08): вся арифметика
       остатков/превышений — composables/items/feoPlanned/*, строки/меню/диалоги —
       components/items/feo-planned/*, стили — styles/feo-planned-select.css +
       переиспользуемый feoTreeRails.css. Поведение не менялось.
       Псевдо-вариант «Вне плана (новая позиция)» убран (сессия 2026-08-05) — владелец:
       позицию, которой нет в плане, заводят кнопкой «Создать в плане закупок» ниже. -->
  <div v-if="categoryId != null" class="feo-planned-select" :class="{ 'feo-planned-select--dense': dense }">
    <!-- skipLast: заявка привязана к промежуточному уровню — плановые позиции недоступны -->
    <template v-if="skipLast">
      <div class="feo-tree-row feo-tree-row--pseudo feo-planned-disabled">
        <v-icon size="16" icon="mdi-clipboard-list-outline" class="mr-1" />
        <span class="feo-tree-name">Заявка привязана к промежуточному уровню ФЭО — плановые позиции недоступны</span>
      </div>
    </template>

    <template v-else>
      <div class="feo-planned-title text-caption font-weight-medium d-flex align-center ga-1 mb-1">
        <v-icon size="16" icon="mdi-clipboard-list-outline" />
        <span>Плановые позиции плана закупок</span>
      </div>

      <template v-if="loading">
        <v-skeleton-loader type="list-item-two-line@2" />
      </template>

      <template v-else>
        <!-- Корневая строка — выбранная категория, не кликается -->
        <div class="feo-tree-row feo-tree-row--root">
          <v-icon size="15" class="mr-1 flex-shrink-0" icon="mdi-folder" color="#3B82F6" />
          <span class="feo-tree-name feo-tree-name--root">{{ rows.categoryName.value }}</span>
        </div>

        <FeoPlannedMatchSuggestions
          :candidates="candidates"
          :readonly="readonly"
          :same-category-candidates="match.sameCategoryCandidates.value"
          :other-category-candidates="match.otherCategoryCandidates.value"
          :score-color="match.scoreColor"
          @bind="match.bindCandidate"
          @reject="match.rejectSuggestions"
        />

        <FeoPlannedDenseSelect
          v-if="dense"
          v-model:dense-menu-open="denseMenuOpen"
          :dense-summary-row="rows.denseSummaryRow.value"
          :dense-residual-display="rows.denseResidualDisplay.value"
          :ghost-row="rows.ghostRow.value"
          :model-value-id="modelValue?.id"
          :filtered-items="rows.filteredItems.value"
          :readonly="readonly"
          :selected-key="rows.selectedKey.value"
          :suggest-key="suggestKey"
          :suggest-reason="suggestReason"
          :fmt="rows.fmt"
          :row-display-props="rows.rowDisplayProps"
          :kind-chip-color="rows.kindChipColor"
          :kind-chip-label="rows.kindChipLabel"
          @toggle="(row, event) => rows.onItemRadioClick(row, event)"
          @select="rows.selectItem"
          @open-consumers="consumers.openConsumers"
          @delete="rows.deletePlannedItem"
          @detach-ghost="rows.detachGhost"
          @create-entry="openCreateEntry"
        />

        <FeoPlannedExpandedList
          v-else
          :ghost-row="rows.ghostRow.value"
          :model-value-id="modelValue?.id"
          :filtered-items="rows.filteredItems.value"
          :readonly="readonly"
          :selected-key="rows.selectedKey.value"
          :suggest-key="suggestKey"
          :suggest-reason="suggestReason"
          :row-display-props="rows.rowDisplayProps"
          :kind-chip-color="rows.kindChipColor"
          :kind-chip-label="rows.kindChipLabel"
          @toggle="(row, event) => rows.onItemRadioClick(row, event)"
          @select="rows.selectItem"
          @open-consumers="consumers.openConsumers"
          @delete="rows.deletePlannedItem"
          @detach-ghost="rows.detachGhost"
          @create-entry="openCreateEntry"
        />
      </template>
    </template>

    <FeoPlannedCreateDialog
      v-model="create.createDialog.value"
      :category-name="rows.categoryName.value"
      :form="create.createForm"
      :amount-is-computed="create.createAmountIsComputed.value"
      :price-caption="create.createPriceCaption.value"
      :saving="create.createSaving.value"
      @save="create.saveCreateDialog"
    />

    <FeoPlannedDuplicateDialog
      v-model="create.duplicateDialog.value"
      :duplicate-info="create.duplicateInfo.value"
      :attach-blocked-reason="create.attachBlockedReason.value"
      :attach-disabled="create.attachDisabled.value"
      :saving="create.createSaving.value"
      :fmt="rows.fmt"
      @attach="create.confirmAttachDuplicate"
      @create-duplicate="create.confirmCreateDuplicate"
    />

    <FeoPlannedBulkChooserDialog
      v-model="bulk.bulkChooserDialog.value"
      v-model:mode="bulk.bulkMode.value"
      v-model:single-name="bulk.bulkSingleName.value"
      :category-name="rows.categoryName.value"
      :bulk-items="bulkItems"
      :manual-checked="bulk.manualChecked.value"
      :bulk-total-amount="bulk.bulkTotalAmount.value"
      :bulk-per-item-candidates="bulk.bulkPerItemCandidates.value"
      :bulk-skipped-linked-count="bulk.bulkSkippedLinkedCount.value"
      :bulk-preview-rows="bulk.bulkPreviewRows.value"
      :bulk-preview-total="bulk.bulkPreviewTotal.value"
      :bulk-creating="bulk.bulkCreating.value"
      :fmt="rows.fmt"
      @toggle-manual="bulk.toggleManualChecked"
      @create="bulk.runBulkCreate"
    />

    <FeoPlannedConsumersDialog
      v-model="consumers.consumersDialog.open"
      :loading="consumers.consumersDialog.loading"
      :error="consumers.consumersDialog.error"
      :row="consumers.consumersDialog.row"
      :data="consumers.consumersDialog.data"
      :dialog-pending-items="consumers.dialogPendingItems.value"
      :dialog-other-purchases="consumers.dialogOtherPurchases.value"
      :dialog-other-wishes="consumers.dialogOtherWishes.value"
      :dialog-is-empty="consumers.dialogIsEmpty.value"
      :dialog-form-label="consumers.dialogFormLabel.value"
      :fmt="rows.fmt"
      :fmt-num="rows.fmtNum"
      :consumed-for="rows.consumedFor"
      :plan-residual-display="rows.planResidualDisplay"
      @go-to-purchase="consumers.goToPurchase"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import '@/styles/feo-planned-select.css'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection } from '@/composables/useFeoPlannedResiduals'
import type { FeoMatchCandidate } from '@/composables/useFeoPlanMatching'
import { useToast, type ToastType } from '@/composables/useToast'
import { useFeoPlannedRows } from '@/composables/items/feoPlanned/useFeoPlannedRows'
import { useFeoPlannedMatch } from '@/composables/items/feoPlanned/useFeoPlannedMatch'
import { useFeoPlannedCreate } from '@/composables/items/feoPlanned/useFeoPlannedCreate'
import { useFeoPlannedBulk } from '@/composables/items/feoPlanned/useFeoPlannedBulk'
import { useFeoPlannedConsumers } from '@/composables/items/feoPlanned/useFeoPlannedConsumers'
import FeoPlannedMatchSuggestions from './feo-planned/FeoPlannedMatchSuggestions.vue'
import FeoPlannedDenseSelect from './feo-planned/FeoPlannedDenseSelect.vue'
import FeoPlannedExpandedList from './feo-planned/FeoPlannedExpandedList.vue'
import FeoPlannedCreateDialog from './feo-planned/FeoPlannedCreateDialog.vue'
import FeoPlannedDuplicateDialog from './feo-planned/FeoPlannedDuplicateDialog.vue'
import FeoPlannedBulkChooserDialog from './feo-planned/FeoPlannedBulkChooserDialog.vue'
import FeoPlannedConsumersDialog from './feo-planned/FeoPlannedConsumersDialog.vue'

const props = defineProps<{
  modelValue: FeoPlanSelection | null
  categoryId: number | null
  nodes: FeoNode[]
  items: FeoPlanPosition[]
  /** Сумма позиций заявки — чтобы показать нехватку остатка при выборе строки. */
  amount?: number | null
  /** Составной ключ (`${kind}:${id}`) авто-подсказанной строки — см. FeoPlanPosition.key. */
  suggestKey?: string | null
  suggestReason?: string | null
  /** Шаг 4 плана zany-fluttering-mountain.md: кандидаты POST /feo-planned-items/match
   *  (похожие по имени плановые позиции, со score) — опционально; без пропа блок
   *  ниже НЕ рендерится (PurchaseItemsEditor.vue его не передаёт, back-compat). */
  candidates?: FeoMatchCandidate[]
  loading?: boolean
  readonly?: boolean
  skipLast?: boolean
  dense?: boolean
  /** Данные уже введённой позиции закупки — кнопка «Создать в плане закупок»
   *  заполняет ими форму диалога вместо пустых полей (владелец: «пусть берёт
   *  данные уже введённой позиции»). Опционально — без пропа диалог открывается
   *  пустым, как раньше. */
  prefill?: { name?: string | null; quantity?: number | null; unit?: string | null; amount?: number | null }
  /** Позиции заявки/закупки — доступны ТОЛЬКО у «шапочного» экземпляра компонента
   *  (CreateOrderView.vue/WishesView.vue, один на всю заявку/закупку), НЕ у построчных
   *  (dense-режим внутри PurchaseItemsEditor — там prefill уже про ОДНУ строку и старый
   *  однопозиционный диалог остаётся как есть). Наличие и непустота этого пропа — сигнал
   *  открывать диалог ВЫБОРА СПОСОБА вместо старого прямого диалога создания (жалоба
   *  владельца, сессия 2026-08-17: кнопка создавала ровно одну плановую позицию на имя
   *  первого товара и на всю НМЦД закупки/заявки — 6 из 7 товаров заявки теряли план). */
  bulkItems?: { idx: number; name: string; quantity: number | null; unit: string | null; amount: number | null; linked: boolean }[]
  /** Заголовок заявки/закупки — дефолт имени для варианта «одна общая позиция» (вариант б):
   *  задаётся пользователем, но предзаполняется НЕ именем первого товара (как было раньше),
   *  а названием самой заявки/закупки. */
  bulkTitle?: string | null
  /** Жалоба владельца (сессия 2026-08-19): «включаю переключатель — должно стать выбрано
   *  1500, остаток 0... а сейчас включаю-выключаю, там по-прежнему выбрано 0». row.consumed/
   *  row.residual приходят С СЕРВЕРА (/feo-categories/plan-positions, exclude_purchase_id —
   *  своя закупка НЕ учтена, это верно и не трогается), но выбор, сделанный ПРЯМО СЕЙЧАС в
   *  этой форме, в них не отражён. Карта feo_planned_item_id → сумма позиций ЭТОЙ формы
   *  (PurchaseItemsEditor.vue::pendingByPlannedItem) добавляется поверх серверных чисел —
   *  см. pendingFor/consumedFor/residualFor в useFeoPlannedRows.ts. Только для
   *  kind==='planned_item' (id — это id FeoPlannedItem; у plan_position/feo_article своей
   *  плановой позиции нет). */
  pendingByPlannedItem?: Record<number, number> | null
  /** Расшифровка «Кто расходует план» (владелец, 2026-08-20): та же выборка, что дала
   *  pendingByPlannedItem, но самими позициями (имя/кол-во/ед./сумма) — построена в
   *  PurchaseItemsEditor.vue::pendingItemsByPlannedItem той же фильтрацией (pid != null,
   *  !over_plan). Диалог «Кто расходует план» (см. openConsumers/pendingItemsFor в
   *  useFeoPlannedRows.ts/useFeoPlannedConsumers.ts) показывает их отдельным блоком
   *  «в этой заявке/закупке (сейчас на экране)» — это и есть причина, по которой
   *  consumedFor(row) > row.consumed с сервера, и без этого блока расшифровка молча не
   *  сходится со строкой (жалоба владельца: «съедено 0 ₽» в диалоге при «выбрано 11 281»
   *  в строке). */
  pendingItemsByPlannedItem?: Record<number, { name: string; quantity: number | null; unit: string | null; amount: number }[]> | null
  /** Жалоба владельца (сессия 2026-08-19): «Хочу удалить плановую позицию... где эта
   *  корзиночка?» — корзинка уже была в ШАПКЕ карточки закупки (CreateOrderView.vue::
   *  deleteHeadPlannedItem, коммит 5901986), но не в этом компоненте, через который
   *  реально идёт построчный/dense выбор. purchaseId — «откуда удаляют» (см.
   *  deletePlannedItem в useFeoPlannedRows.ts и backend/app/routers/feo_planned_items.py::
   *  delete_planned_item) — необязателен: PurchaseItemsEditor.vue его знает и
   *  прокидывает, форма заявки (ещё не закупка) — нет, и это нормально. */
  purchaseId?: number | null
  /** Дефект 2 (владелец, 2026-08-20): «При создании заявки случайно создали плановую
   *  позицию неправильно, надо удалить» — та же роль, что purchaseId выше, но для
   *  формы ЗАЯВКИ (WishesView.vue), у которой закупки ещё нет и purchase_id взять
   *  неоткуда. wish_id уходит в DELETE (см. deletePlannedItem) — бэкенд считает
   *  ссылки wish_items ЭТОЙ заявки «своими» и снимает их молча, как purchase_id
   *  снимает ссылки своей закупки. Отдельный проп от excludeWishId ниже: тот только
   *  влияет на СЧЁТ «съедено» в GET consumers, этот — на право удалить. */
  wishId?: number | null
  /** Та же заявка/закупка, что родитель передал useFeoPlannedResiduals как
   *  excludeWishId/excludePurchaseId при загрузке props.items (WishesView.vue —
   *  editingWishId, CreateOrderView.vue/PurchaseItemsEditor.vue — purchaseId) —
   *  чтобы GET /feo-planned-items/{id}/consumers (см. openConsumers выше) считал
   *  «съедено» ТЕМИ ЖЕ исключениями, что и уже показанное row.consumed, иначе два
   *  числа на экране разойдутся между собой. */
  excludeWishId?: number | null
  excludePurchaseId?: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: FeoPlanSelection | null]
  /** Пользователь нажал «Привязать» на предложенном кандидате (Шаг 4) — родитель
   *  фиксирует, что привязку выбрал человек (флаг подтверждения, см.
   *  POST /feo-planned-items/confirm-wish-plan-match). update:modelValue тоже
   *  эмитится (сама привязка), это отдельное событие — только про подтверждение. */
  'candidate-confirmed': [candidate: FeoMatchCandidate]
  /** Плановая позиция создана диалогом «Создать в плане закупок» (POST /feo-planned-items/) —
   *  родитель должен перезагрузить список плановых позиций (напр. useFeoPlannedResiduals.reloadPlanned). */
  'planned-item-created': []
  /** Плановая позиция удалена корзинкой прямо из строки списка (см. deletePlannedItem) —
   *  родитель должен перезагрузить список плановых позиций, тем же обработчиком, что
   *  и на 'planned-item-created' (owner: «оставить перечень плановых, для возможности
   *  их удаления и высвобождения денег»). */
  'planned-item-deleted': []
  /** Диалог выбора способа (bulkItems) создал 1+ плановых позиций через
   *  POST /feo-planned-items/bulk — родитель обязан привязать каждую созданную
   *  позицию к её товару заявки/закупки по idx (results[i].idx — индекс в том же
   *  массиве, что был передан через bulkItems; null у режима «одна общая позиция»,
   *  там привязка приходит через update:modelValue как обычно). */
  'bulk-items-created': [payload: { mode: 'per_item' | 'single' | 'manual'; results: { idx: number | null; id: number }[] }]
}>()

const denseMenuOpen = ref(false)

// Snackbar — единый механизм (useToast + ToastContainer, смонтирован в App.vue).
const toast = useToast()
function showSnack(text: string, color: ToastType = 'success') {
  toast.addToast(text, color)
}

const rows = useFeoPlannedRows({ props, emit, showSnack })
const match = useFeoPlannedMatch({ props, emit, denseMenuOpen })
const create = useFeoPlannedCreate({ props, emit, showSnack, fmt: rows.fmt, fmtNum: rows.fmtNum })
const bulk = useFeoPlannedBulk({ props, emit, showSnack })
const consumers = useFeoPlannedConsumers({ props, pendingItemsFor: rows.pendingItemsFor })

// Владелец (сессия 2026-08-17): «должна сразу предлагать, как сделать» — на
// «шапочном» экземпляре (bulkItems передан и непуст) кнопка открывает диалог выбора
// способа вместо старого прямого диалога создания. Построчные (dense/prefill
// одной позиции внутри PurchaseItemsEditor) bulkItems не получают и продолжают
// пользоваться старым простым create.openCreateDialog — там кнопка и так «про эту позицию».
function openCreateEntry() {
  if (props.readonly || props.categoryId == null) return
  if (props.bulkItems && props.bulkItems.length > 0) {
    bulk.openBulkChooserDialog()
  } else {
    create.openCreateDialog()
  }
}
</script>

<style scoped src="./feoTreeRails.css"></style>
