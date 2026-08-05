<template>
  <!-- Выбор ПЛАНОВОЙ ПОЗИЦИИ (единый источник /feo-categories/plan-positions —
       конечный элемент дерева ФЭО с планом, статья ФЭО с планом, или детализация
       Ур.5 FeoPlannedItem) — визуально продолжение дерева ФЭО (FeoTreeSelect): те же
       рельсы/локти (feoTreeRails.css), корневая строка — выбранная категория, ниже —
       её плановые позиции (сама категория + дочерние конечные элементы). Строка —
       <div role="switch">, обработчик клика висит на самом div (НЕ на <label>, чтобы
       браузер не удваивал клик синтетическим событием на вложенном контроле — см. баг
       в onItemRadioClick); <v-switch> внутри — чисто визуальный индикатор,
       pointer-events:none. Клик по всей строке = выбор, повторный клик
       по уже выбранной строке снимает выбор (см. onItemRadioClick).
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
          <span class="feo-tree-name feo-tree-name--root">{{ categoryName }}</span>
        </div>

        <!-- Компактный (dense) режим — свёрнутая строка с разворотом по клику -->
        <template v-if="dense">
          <v-menu v-model="denseMenuOpen" :close-on-content-click="false" location="bottom start">
            <template #activator="{ props: menuActivatorProps }">
              <div v-bind="menuActivatorProps" class="feo-tree-row feo-planned-dense-row">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow" />
                <span class="feo-tree-name">{{ denseSummaryLabel }}</span>
                <v-icon size="16" icon="mdi-chevron-down" class="flex-shrink-0" />
              </div>
            </template>
            <v-card class="feo-planned-dense-menu pa-1">
              <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow feo-tree-elbow--open" />
                <span class="feo-tree-name">#{{ modelValue?.id }} (позиция удалена из плана)</span>
                <v-btn size="x-small" variant="text" color="error" @click.stop="detachGhost">Отвязать</v-btn>
              </div>
              <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
                <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
                <span class="feo-tree-name">В этой категории нет плановых позиций</span>
                <v-btn size="x-small" variant="text" color="primary" :disabled="readonly" @click.stop="openCreateDialog">Создать в плане закупок</v-btn>
              </div>
              <div
                v-for="row in filteredItems"
                :key="row.key"
                class="feo-tree-row"
                :class="{ 'feo-tree-row--selected': selectedKey === row.key, 'feo-tree-row--clickable': !readonly }"
                :title="selectedKey === row.key ? 'Нажмите ещё раз, чтобы снять выбор' : undefined"
                role="switch"
                :aria-checked="selectedKey === row.key"
                :tabindex="readonly ? -1 : 0"
                @click="onItemRadioClick(row, $event)"
                @keydown.enter.prevent="onItemRadioClick(row, $event)"
                @keydown.space.prevent="onItemRadioClick(row, $event)"
              >
                <span class="feo-tree-rail" />
                <span class="feo-tree-elbow feo-tree-elbow--open" />
                <v-switch
                  :model-value="selectedKey === row.key"
                  :disabled="readonly"
                  density="compact"
                  hide-details
                  inset
                  color="primary"
                  class="feo-planned-switch"
                />
                <span class="feo-tree-name">
                  {{ row.name }}
                  <span class="feo-planned-qty text-caption text-medium-emphasis">{{ fmtQty(row) }}</span>
                  <v-chip size="x-small" :color="kindChipColor(row.kind)" variant="tonal" class="ml-1">{{ kindChipLabel(row.kind) }}</v-chip>
                  <v-chip
                    v-if="suggestKey === row.key"
                    size="x-small"
                    color="teal"
                    variant="tonal"
                    prepend-icon="mdi-auto-fix"
                    class="ml-1"
                    @click.stop="selectItem(row)"
                  >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
                </span>
                <span class="feo-tree-residual">
                  план {{ fmt(row.planned_amount) }} · выбрано {{ fmt(row.consumed) }} ·
                  <span :class="{ 'feo-planned-shortfall': isShort(row) }">остаток {{ fmt(row.residual) }}</span>
                  <span v-if="isShort(row)" class="feo-planned-shortfall-note"> — не хватает {{ fmt(Math.abs(shortfall(row))) }}</span>
                </span>
              </div>
            </v-card>
          </v-menu>
        </template>

        <!-- Обычный (развёрнутый) режим -->
        <template v-else>
          <!-- «Призрак»: modelValue указывает на позицию, которой нет в items -->
          <div v-if="ghostRow" class="feo-tree-row feo-planned-ghost">
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow feo-tree-elbow--open" />
            <span class="feo-tree-name">#{{ modelValue?.id }} (позиция удалена из плана)</span>
            <v-btn size="x-small" variant="text" color="error" @click="detachGhost">Отвязать</v-btn>
          </div>

          <div v-if="filteredItems.length === 0" class="feo-tree-row feo-tree-row--pseudo">
            <span class="feo-tree-rail" /><span class="feo-tree-elbow feo-tree-elbow--open" />
            <span class="feo-tree-name">В этой категории нет плановых позиций</span>
            <v-btn size="x-small" variant="text" color="primary" :disabled="readonly" @click="openCreateDialog">Создать в плане закупок</v-btn>
          </div>

          <div
            v-for="row in filteredItems"
            :key="row.key"
            class="feo-tree-row"
            :class="{ 'feo-tree-row--selected': selectedKey === row.key, 'feo-tree-row--clickable': !readonly }"
            :title="selectedKey === row.key ? 'Нажмите ещё раз, чтобы снять выбор' : undefined"
            role="switch"
            :aria-checked="selectedKey === row.key"
            :tabindex="readonly ? -1 : 0"
            @click="onItemRadioClick(row, $event)"
            @keydown.enter.prevent="onItemRadioClick(row, $event)"
            @keydown.space.prevent="onItemRadioClick(row, $event)"
          >
            <span class="feo-tree-rail" />
            <span class="feo-tree-elbow feo-tree-elbow--open" />
            <v-switch
              :model-value="selectedKey === row.key"
              :disabled="readonly"
              density="compact"
              hide-details
              inset
              color="primary"
              class="feo-planned-switch"
            />
            <span class="feo-tree-name">
              {{ row.name }}
              <span class="feo-planned-qty text-caption text-medium-emphasis">{{ fmtQty(row) }}</span>
              <v-chip size="x-small" :color="kindChipColor(row.kind)" variant="tonal" class="ml-1">{{ kindChipLabel(row.kind) }}</v-chip>
              <v-chip
                v-if="suggestKey === row.key"
                size="x-small"
                color="teal"
                variant="tonal"
                prepend-icon="mdi-auto-fix"
                class="ml-1"
                @click.stop="selectItem(row)"
              >{{ suggestReason || 'Похоже совпадает' }}</v-chip>
            </span>
            <span class="feo-tree-residual">
              план {{ fmt(row.planned_amount) }} · выбрано {{ fmt(row.consumed) }} ·
              <span :class="{ 'feo-planned-shortfall': isShort(row) }">остаток {{ fmt(row.residual) }}</span>
              <span v-if="isShort(row)" class="feo-planned-shortfall-note"> — не хватает {{ fmt(Math.abs(shortfall(row))) }}</span>
            </span>
          </div>

          <div class="mt-1">
            <v-btn size="x-small" variant="text" color="primary" prepend-icon="mdi-plus" :disabled="readonly" @click="openCreateDialog">
              Создать в плане закупок
            </v-btn>
          </div>
        </template>
      </template>
    </template>

    <!-- Диалог создания плановой позиции (Ур.5 FeoPlannedItem) прямо в текущей категории —
         POST /feo-planned-items/, без перехода на другую страницу и потери введённых данных
         формы (см. баг «кнопка ничего не делает», сессия 2026-08-05). -->
    <v-dialog v-model="createDialog" max-width="420" persistent>
      <v-card>
        <v-card-title class="text-subtitle-1">Новая плановая позиция</v-card-title>
        <v-card-text>
          <div class="text-caption text-medium-emphasis mb-2">Категория: {{ categoryName }}</div>
          <v-text-field
            v-model="createForm.name"
            label="Наименование *"
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-2"
            autofocus
          />
          <v-text-field
            v-model.number="createForm.quantity"
            type="number"
            label="Количество"
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-2"
          />
          <v-text-field
            v-model="createForm.unit"
            label="Ед. изм."
            variant="outlined"
            density="compact"
            hide-details="auto"
            class="mb-2"
          />
          <v-text-field
            v-model.number="createForm.amount"
            type="number"
            label="Сумма плана, ₽"
            variant="outlined"
            density="compact"
            hide-details="auto"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="createSaving" @click="createDialog = false">Отмена</v-btn>
          <v-btn color="primary" variant="flat" :loading="createSaving" @click="saveCreateDialog">Создать</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snack.show" :color="snack.color" :timeout="snack.color === 'error' ? -1 : 3000" location="bottom right">
      {{ snack.text }}
      <template #actions>
        <v-btn variant="text" @click="snack.show = false">Закрыть</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import type { FeoNode } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition, FeoPlanSelection, FeoPlanKind } from '@/composables/useFeoPlannedResiduals'

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
  loading?: boolean
  readonly?: boolean
  skipLast?: boolean
  dense?: boolean
  /** Данные уже введённой позиции закупки — кнопка «Создать в плане закупок»
   *  заполняет ими форму диалога вместо пустых полей (владелец: «пусть берёт
   *  данные уже введённой позиции»). Опционально — без пропа диалог открывается
   *  пустым, как раньше. */
  prefill?: { name?: string | null; quantity?: number | null; unit?: string | null; amount?: number | null }
}>()

const emit = defineEmits<{
  'update:modelValue': [val: FeoPlanSelection | null]
  /** Плановая позиция создана диалогом «Создать в плане закупок» (POST /feo-planned-items/) —
   *  родитель должен перезагрузить список плановых позиций (напр. useFeoPlannedResiduals.reloadPlanned). */
  'planned-item-created': []
}>()

const denseMenuOpen = ref(false)

const selectedNode = computed((): FeoNode | undefined =>
  props.categoryId != null ? props.nodes.find(n => n.id === props.categoryId) : undefined
)

const categoryName = computed((): string => selectedNode.value?.name?.trim() ?? '—')

const selectedKey = computed((): string | null =>
  props.modelValue ? `${props.modelValue.kind}:${props.modelValue.id}` : null
)

// БАГ 1 (сессия 2026-08-05): раньше фильтрация шла обходом props.nodes
// (collectDescendantIds), а nodes приходит из useFeoLeaves → filterFundedNodes,
// который ВЫРЕЗАЕТ конечные категории без собственного budget — даже если у них
// заполнены planned_quantity/planned_amount (плановая позиция). Из-за этого
// «В этой категории нет плановых позиций» показывалось для категорий, у которых
// план ЕСТЬ, просто их лист не прошёл фильтр finansирования. Бэкенд
// GET /feo-categories/plan-positions теперь отдаёт на каждой строке ancestor_ids
// (id всех предков ДО корня) — матчим напрямую по нему, без обхода дерева.
const filteredItems = computed((): FeoPlanPosition[] => {
  if (props.categoryId == null) return []
  const cid = props.categoryId
  return props.items.filter(r => r.category_id === cid || (r.ancestor_ids || []).includes(cid))
})

// modelValue ссылается на строку, которой больше нет среди актуальных (отфильтрованных
// по категории/потомкам) items — либо позицию удалили из плана закупок, либо она
// принадлежит категории вне текущей ветки дерева.
const ghostRow = computed((): boolean => {
  if (!props.modelValue) return false
  return !filteredItems.value.some(r => r.key === selectedKey.value)
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
}

function fmtQty(row: FeoPlanPosition): string {
  const qty = row.planned_quantity != null ? row.planned_quantity.toLocaleString('ru-RU') : '—'
  return `${qty} ${row.unit || ''}`.trim()
}

function shortfall(row: FeoPlanPosition): number {
  if (props.amount == null) return 0
  return row.residual - props.amount
}

function isShort(row: FeoPlanPosition): boolean {
  return props.amount != null && shortfall(row) < 0
}

const KIND_CHIP_COLOR: Record<FeoPlanKind, string> = {
  plan_position: 'teal',
  feo_article: 'grey',
  planned_item: 'indigo',
}
const KIND_CHIP_LABEL: Record<FeoPlanKind, string> = {
  plan_position: 'плановая позиция',
  feo_article: 'статья ФЭО с планом',
  planned_item: 'детализация',
}
function kindChipColor(kind: FeoPlanKind): string { return KIND_CHIP_COLOR[kind] }
function kindChipLabel(kind: FeoPlanKind): string { return KIND_CHIP_LABEL[kind] }

const denseSummaryLabel = computed((): string => {
  const row = selectedKey.value != null ? filteredItems.value.find(r => r.key === selectedKey.value) : undefined
  if (row) return `${row.name} — план ${fmt(row.planned_amount)} · остаток ${fmt(row.residual)}`
  return 'Выбрать плановую позицию'
})

function selectItem(row: FeoPlanPosition) {
  if (props.readonly) return
  emit('update:modelValue', { kind: row.kind, id: row.id })
}

// БАГ 2 (сессия 2026-08-05, добор 2026-08-05): изначально <input type="radio"> лежал
// ВНУТРИ <label class="feo-tree-row">, а обработчик висел на самом <input>. Клик по
// <label> браузер сам транслирует во ВТОРОЙ синтетический клик по вложенному <input> —
// onItemRadioClick срабатывал дважды за один клик пользователя: первый раз выбирал
// строку, второй тут же видел selectedKey === row.key и снимал выбор. Внешне — «клик
// ничего не делает». Исправлено: обёртка теперь <div role="switch">, обработчик висит
// на самом div (ровно один клик = ровно один вызов). Индикатор выбора (сессия
// 2026-08-06, владелец: «точка выбора не садится на позицию — сделай переключатель»)
// заменён с input[type=radio] на <v-switch> — чисто визуальный, pointer-events:none
// в CSS, своих событий не порождает. Источник правды — Vue-состояние (props.modelValue),
// а не DOM-состояние переключателя. Доступность: role="switch" + aria-checked + tabindex
// + Enter/Space.
function onItemRadioClick(row: FeoPlanPosition, event?: Event) {
  if (props.readonly) return
  event?.preventDefault()
  if (selectedKey.value === row.key) {
    emit('update:modelValue', null)
  } else {
    selectItem(row)
  }
}

function detachGhost() {
  if (props.readonly) return
  emit('update:modelValue', null)
}

// БАГ 3 (сессия 2026-08-05): раньше кнопка «Создать в плане закупок» делала
// router.push('/subsidies') — уводила пользователя со страницы, теряя введённые данные
// формы, и ничего не создавала. Теперь — диалог тут же, POST /feo-planned-items/
// (контракт см. backend/app/routers/feo_planned_items.py), затем родитель
// перезагружает список ('planned-item-created') и созданная позиция выбирается сразу.
const createDialog = ref(false)
const createForm = reactive<{ name: string; quantity: number | null; unit: string; amount: number | null }>({
  name: '', quantity: null, unit: '', amount: null,
})
const createSaving = ref(false)
const snack = ref<{ show: boolean; text: string; color: 'success' | 'error' }>({ show: false, text: '', color: 'success' })

function showSnack(text: string, color: 'success' | 'error' = 'success') {
  snack.value = { show: true, text, color }
}

function openCreateDialog() {
  if (props.readonly || props.categoryId == null) return
  // Предзаполнение из уже введённой позиции закупки (см. prefill в defineProps),
  // с фолбэком на пустые значения — как было раньше без пропа.
  createForm.name = props.prefill?.name ?? ''
  createForm.quantity = props.prefill?.quantity ?? null
  createForm.unit = props.prefill?.unit ?? ''
  createForm.amount = props.prefill?.amount ?? null
  createDialog.value = true
}

async function saveCreateDialog() {
  if (props.categoryId == null) return
  if (!createForm.name.trim()) {
    showSnack('Укажите наименование', 'error')
    return
  }
  createSaving.value = true
  try {
    const created = await apiFetch<{ id: number }>('/feo-planned-items/', {
      method: 'POST',
      body: JSON.stringify({
        feo_category_id: props.categoryId,
        name: createForm.name.trim(),
        quantity: createForm.quantity,
        unit: createForm.unit.trim() || null,
        amount: createForm.amount,
      }),
    })
    createDialog.value = false
    emit('planned-item-created')
    emit('update:modelValue', { kind: 'planned_item', id: created.id })
    showSnack('Плановая позиция создана')
  } catch (e: any) {
    showSnack(e?.payload?.message || e?.message || 'Не удалось создать плановую позицию', 'error')
  } finally {
    createSaving.value = false
  }
}
</script>

<style scoped src="./feoTreeRails.css"></style>
<style scoped>
.feo-planned-select {
  margin-top: 4px;
}
.feo-planned-title {
  color: var(--crm-text-secondary);
}
.feo-planned-disabled {
  cursor: default;
  opacity: 0.85;
}
.feo-planned-switch {
  flex-shrink: 0;
  margin-top: -4px;
  margin-bottom: -4px;
  /* Чисто визуальный индикатор — клик обрабатывается на обёртке .feo-tree-row (div
     role="switch"), не на самом переключателе (иначе браузер генерит второй
     синтетический клик по клику на обёртке — двойное срабатывание onItemRadioClick,
     см. комментарий в <script setup>). */
  pointer-events: none;
}
.feo-planned-switch :deep(.v-selection-control) {
  min-height: unset;
}
.feo-planned-select .feo-tree-row--clickable {
  cursor: pointer;
}
.feo-planned-select .feo-tree-row:not(.feo-tree-row--clickable) {
  cursor: default;
}
.feo-planned-select .feo-tree-row--clickable:focus-visible {
  outline: 2px solid #3B82F6;
  outline-offset: -2px;
}
.feo-planned-qty {
  margin-left: 6px;
}
.feo-planned-shortfall {
  color: #EF4444;
  font-weight: 700;
}
.feo-planned-shortfall-note {
  color: #EF4444;
  font-weight: 700;
}
.feo-planned-ghost {
  color: #EF4444;
}
.feo-planned-ghost .feo-tree-name {
  color: #EF4444;
}
.feo-planned-dense-row {
  cursor: pointer;
}
.feo-planned-dense-menu {
  max-height: 360px;
  overflow-y: auto;
  min-width: 320px;
}
</style>
