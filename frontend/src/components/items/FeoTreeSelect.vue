<template>
  <!-- Дерево-выбор категории ФЭО. Drop-in замена FeoCascadeSelect: те же props/emits,
       но вместо каскада последовательных селектов — одно поле с полным путём
       и выпадающее дерево с поиском. Клик по любому узлу (папке ИЛИ листу) эмитит
       update:modelValue с его id — это нужно для пропагации уровня при мультивыборе
       в PurchaseItemsEditor (см. onItemFeoChange). Клик по листу дополнительно
       закрывает меню, клик по папке — оставляет открытым (углубление в дерево).
       Опциональный rootLabel рисует «ствол» (название субсидии) первой строкой —
       узлы уровня 1 становятся его детьми. Ствол не выбирается, только
       сворачивает/разворачивает своё поддерево. -->
  <div class="feo-tree-select" :class="{ 'is-horizontal': horizontal }">
    <template v-if="nodes.length === 0">
      <v-text-field
        model-value=""
        density="compact"
        variant="outlined"
        hide-details
        disabled
        placeholder="Нет данных ФЭО"
        class="my-1"
      />
    </template>

    <template v-else>
      <v-menu
        v-model="menuOpen"
        :disabled="!!readonly"
        :close-on-content-click="false"
        location="bottom start"
        transition="scale-transition"
        :min-width="menuMinWidth"
        :max-width="menuMaxWidth"
        content-class="feo-tree-menu-content"
      >
        <template #activator="{ props: activatorProps }">
          <div ref="fieldWrapEl">
            <!-- v-textarea вместо v-text-field: путь переносится и виден целиком,
                 а не обрезается многоточием в одну строку. Label встроен в поле
                 (как у соседних полей формы), поэтому отдельная подпись сверху
                 родителям больше не нужна.
                 Жалоба владельца (повторно, 2026-08-12): в карточке закупки (строка
                 таблицы позиций, :horizontal + density=compact, поле глубоко внутри
                 expand-row с transition) Vuetify-шный auto-grow считает высоту НЕВЕРНО —
                 остаётся зафиксирован на высоте одной строки (32px), хотя реальный текст
                 требует больше (scrollHeight 44px), и путь обрезается внутренним скроллом
                 textarea. В панели субсидии (comfortable density, обычный v-card-text,
                 без table/transition-вложенности) тот же auto-grow считает верно — баг
                 именно в измерении высоты в этом глубоко вложенном/анимированном контексте.
                 Фикс: не полагаемся на встроенный auto-grow вообще — измеряем и
                 выставляем высоту textarea сами (resizeFeoTextarea, ищет <textarea>
                 через fieldWrapEl — ref прямо на v-textarea здесь не завести: у
                 элемента есть v-bind="activatorProps" (слот-активатор v-menu), из-за
                 чего компилятор мёржит проп ref через _mergeProps и теряет спец-
                 обработку строкового/функционального ref для <script setup>). -->
            <v-textarea
              v-bind="activatorProps"
              :model-value="selectedPath"
              readonly
              no-resize
              :auto-grow="false"
              rows="1"
              variant="outlined"
              :density="horizontal ? 'compact' : 'comfortable'"
              hide-details
              :label="fieldLabel"
              :error="!!error && !isLeafSelected"
              class="feo-tree-field"
              :class="{ 'feo-tree-field--readonly': readonly }"
            >
              <template #append-inner>
                <v-icon
                  v-if="modelValue != null && !readonly"
                  icon="mdi-close-circle"
                  size="18"
                  class="feo-tree-clear"
                  @click.stop="onClear"
                />
                <v-icon
                  v-if="!readonly"
                  icon="mdi-menu-down"
                  size="20"
                  class="feo-tree-caret"
                  :class="{ 'feo-tree-caret--open': menuOpen }"
                />
              </template>
            </v-textarea>
          </div>
        </template>

        <v-card class="feo-tree-menu-card">
          <!-- Поиск по всему дереву + «Развернуть/Свернуть всё» -->
          <div class="feo-tree-search pa-2 d-flex align-center ga-1">
            <v-text-field
              ref="searchInputEl"
              v-model="searchQuery"
              density="compact"
              variant="outlined"
              hide-details
              clearable
              prepend-inner-icon="mdi-magnify"
              placeholder="Поиск по названию..."
              class="flex-grow-1"
              @click.stop
              @keydown.stop
            />
            <v-tooltip text="Развернуть всё" location="top">
              <template #activator="{ props: tip }">
                <v-btn
                  v-bind="tip"
                  icon="mdi-unfold-more-horizontal"
                  size="small"
                  variant="text"
                  density="comfortable"
                  @click.stop="expandAllNodes"
                />
              </template>
            </v-tooltip>
            <v-tooltip text="Свернуть всё" location="top">
              <template #activator="{ props: tip }">
                <v-btn
                  v-bind="tip"
                  icon="mdi-unfold-less-horizontal"
                  size="small"
                  variant="text"
                  density="comfortable"
                  @click.stop="collapseAllNodes"
                />
              </template>
            </v-tooltip>
          </div>

          <div ref="treeScrollEl" class="feo-tree-scroll">
            <div v-if="flatTree.length === 0" class="pa-3 text-caption text-medium-emphasis">
              Ничего не найдено
            </div>

            <div
              v-for="item in flatTree"
              :key="item.key"
              class="feo-tree-row"
              :class="{
                'feo-tree-row--selected': !item.pseudo && !item.root && item.node!.id === modelValue,
                'feo-tree-row--pseudo': item.pseudo,
                'feo-tree-row--root': item.root,
              }"
              :data-node-id="!item.pseudo && !item.root ? item.node!.id : undefined"
              @click="item.root ? toggleRootExpand() : (item.pseudo ? onPickUnallocated(item.parentId ?? null) : onNodeClick(item.node!))"
            >
              <!-- Направляющие линии предков (пустые/вертикальные ячейки по глубине) -->
              <span
                v-for="(hasLine, li) in item.ancestorLines"
                :key="'r' + li"
                class="feo-tree-rail"
                :class="{ 'feo-tree-rail--line': hasLine }"
              />
              <!-- «Уголок» текущего узла: ├─ если есть следующий сосед, └─ если последний -->
              <span
                v-if="item.depth > 0"
                class="feo-tree-elbow"
                :class="{ 'feo-tree-elbow--open': !item.isLast }"
              />

              <!-- Шеврон: у листьев и псевдо-узла — пустой отступ -->
              <span
                class="feo-tree-chevron"
                @click.stop="item.root ? toggleRootExpand() : (!item.pseudo && !item.node!.is_leaf ? toggleExpand(item.node!.id) : undefined)"
              >
                <v-icon
                  v-if="item.root || (!item.pseudo && !item.node!.is_leaf)"
                  size="16"
                  :icon="(item.root ? rootExpanded : expanded.has(item.node!.id)) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                  color="grey"
                />
                <span v-else style="display:inline-block;width:16px" />
              </span>

              <template v-if="item.root">
                <v-icon size="16" class="mr-1 flex-shrink-0 feo-tree-row-icon" icon="mdi-sitemap" color="#F97316" />
                <span class="feo-tree-name feo-tree-name--root">{{ item.name }}</span>
              </template>
              <template v-else-if="item.pseudo">
                <span class="feo-tree-name feo-tree-name--pseudo">❓ Не определена</span>
              </template>
              <template v-else>
                <v-icon
                  size="15"
                  class="mr-1 flex-shrink-0 feo-tree-row-icon"
                  :icon="item.node!.is_leaf ? 'mdi-file-document-outline' : (expanded.has(item.node!.id) ? 'mdi-folder-open' : 'mdi-folder')"
                  :color="item.node!.is_leaf ? '#22C55E' : '#3B82F6'"
                />
                <span class="feo-tree-name">
                  <template v-if="item.parts">
                    <template v-for="(part, pi) in item.parts" :key="pi">
                      <mark v-if="part.hit" class="feo-tree-hit">{{ part.text }}</mark>
                      <template v-else>{{ part.text }}</template>
                    </template>
                  </template>
                  <template v-else>{{ item.name }}</template>
                </span>
                <span v-if="item.node!.description" class="feo-tree-desc">— {{ item.node!.description }}</span>
                <!-- Задача владельца 2026-08-06: остаток по КАЖДОМУ узлу (не только листу) —
                     nodeAmountDisplayFor учитывает право feo_budget.view_tree_amounts и то,
                     задан ли budget у узла; при отсутствии (nodeAmounts==null — обратная
                     совместимость, либо узел не профинансирован) — старая leaf-only подпись. -->
                <span
                  v-if="nodeAmountDisplayFor(item.node!.id)"
                  class="feo-tree-residual"
                  :class="{ 'feo-tree-residual--negative': nodeAmountDisplayFor(item.node!.id)!.free < 0 }"
                >
                  по ФЭО: {{ fmt(nodeAmountDisplayFor(item.node!.id)!.budget) }} · своб.: {{ fmt(nodeAmountDisplayFor(item.node!.id)!.free) }}
                </span>
                <span v-else-if="item.node!.is_leaf && planNoteFor(item.node!.id)" class="feo-tree-residual">
                  Ост.: {{ fmt(planNoteFor(item.node!.id)!.residual) }}
                </span>
              </template>
            </div>
          </div>
        </v-card>
      </v-menu>

      <!-- Подпись бюджета выбранного листа — как в каскаде -->
      <div v-if="selectedLeafForNote" class="feo-tree-note text-caption text-medium-emphasis mt-1 px-1">
        План: {{ fmt(selectedLeafForNote.budget) }} • Ост.: {{ fmt(selectedLeafForNote.residual) }}
      </div>
      <div v-if="error && !isLeafSelected" class="feo-tree-note text-caption text-error mt-1 px-1">
        Обязательно
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { FeoNode, FeoLeaf } from '@/composables/useFeoLeaves'
import type { FeoPlanPosition } from '@/composables/useFeoPlannedResiduals'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{
  modelValue: number | null
  nodes: FeoNode[]
  leaves: FeoLeaf[]
  readonly?: boolean
  error?: boolean
  horizontal?: boolean
  allowUnallocated?: boolean
  label?: string
  required?: boolean
  rootLabel?: string | null
  /** Плановые позиции (GET /feo-categories/plan-positions) — опциональный источник
   *  «правильного» плана для подписи под полем. leaves (проп выше) берёт план
   *  ИСКЛЮЧИТЕЛЬНО из FeoCategory.budget/feo_amount; у плановых позиций (например,
   *  тех, у кого финансирование задано через planned_quantity × planned_amount, а не
   *  напрямую в категории) budget пуст и подпись показывала «План: 0 ₽», хотя план
   *  реально есть (см. FeoPlanPosition.plan_manual/ordered_residual). Без пропа —
   *  прежнее поведение (обратная совместимость, компонент используется в нескольких
   *  местах и не везде под рукой есть загруженный список плановых позиций). */
  planPositions?: FeoPlanPosition[]
  /** Задача владельца 2026-08-06: «остаток средств напротив каждой категории ФЭО».
   *  Карта {feo_category_id: {budget, free}} — budget = финансирование по ФЭО узла,
   *  free = budget − плановая сумма (та же формула, что «можно добавить/надо убрать»
   *  в дереве субсидий и KPI «Свободно», числа сойдутся). Считается ОДИН раз в родителе
   *  (см. composables/useFeoNodeAmounts) из GET /feo-categories/plan-tree и передаётся
   *  готовым объектом — компонент рендерится в каждой строке таблицы позиций (до ~50
   *  инстансов), пересчитывать роллап тут нельзя (перф). null/undefined — прежнее
   *  поведение (компонент используется в нескольких местах без этого пропа). */
  nodeAmounts?: Record<number, { budget: number; free: number }> | null
}>()

const emit = defineEmits<{
  'update:modelValue': [val: number | null]
  'pick-unallocated': [parentId: number | null]
}>()

// ─── Метка поля (встроена в v-textarea, отдельной подписи-заголовка больше нет) ──
const fieldLabel = computed(() => {
  const base = props.label ?? 'Категория ФЭО'
  return props.required ? `${base} *` : base
})

// ─── Состояние меню ────────────────────────────────────────────────────────
const menuOpen = ref(false)
const searchQuery = ref('')
const expanded = ref<Set<number>>(new Set())
// Раскрыт ли псевдо-корень «ствол» (rootLabel). Актуально только когда hasRoot.
const rootExpanded = ref(true)

const fieldWrapEl = ref<HTMLElement | null>(null)
const treeScrollEl = ref<HTMLElement | null>(null)
const searchInputEl = ref<{ focus?: () => void } | null>(null)
const menuMinWidth = ref(280)
// Числовой px, а не CSS-строка вроде "min(720px, 92vw)": location-strategy
// v-menu (connected) делает Number(props.maxWidth) при расчёте доступного
// места — CSS-функция даёт NaN, и Vuetify молча откатывается к максимально
// доступной ширине вьюпорта (меню растягивалось на весь экран). Считаем
// сами и передаём готовое число.
const menuMaxWidth = ref(720)

// Есть ли ствол (название субсидии), под которым висят реальные узлы уровня 1.
const hasRoot = computed(() => props.rootLabel != null && props.rootLabel.trim() !== '')

// ─── Индексы дерева (строятся один раз на изменение nodes/leaves) ──────────
const nodeById = computed((): Map<number, FeoNode> => {
  const map = new Map<number, FeoNode>()
  for (const n of props.nodes) map.set(n.id, n)
  return map
})

const childrenByParent = computed((): Map<number | null, FeoNode[]> => {
  const map = new Map<number | null, FeoNode[]>()
  for (const n of props.nodes) {
    const key = n.parent_id ?? null
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(n)
  }
  return map
})

const leafById = computed((): Map<number, FeoLeaf> => {
  const map = new Map<number, FeoLeaf>()
  for (const l of props.leaves) map.set(l.id, l)
  return map
})

// Индекс плановых позиций по category_id — только 'plan_position'/'feo_article'
// (у них category_id это id самой конечной категории ФЭО; 'planned_item' — это
// детализация ВНУТРИ категории, её план не подменяет план самой категории).
// Используется как фолбэк для подписи «План/Ост.», когда leafById не даёт budget
// (см. planPositions в defineProps).
//
// Фолбэк для МИГРИРОВАННЫХ категорий-листьев (2026-08-12): план переехал из
// planned_quantity/planned_amount самой категории в отдельные плановые позиции
// (kind='planned_item') внутри неё — у такой категории ОБА поля плана = null,
// и сервер (GET /feo-categories/plan-positions) НЕ эмитит для неё строку
// 'plan_position'/'feo_article' (условие planned_total > 0 не выполняется, см.
// докстринг эндпоинта). Без фолбэка planByCategory для такой категории пуста,
// и planNoteFor ниже показывает «—» вместо реального плана/остатка. Если
// агрегатная строка ('plan_position'/'feo_article') ЕСТЬ — она приоритетна и
// 'planned_item' по-прежнему пропускаются (иначе план задвоится).
const planByCategory = computed((): Map<number, FeoPlanPosition> => {
  const map = new Map<number, FeoPlanPosition>()
  const plannedItemRows = new Map<number, FeoPlanPosition[]>()
  for (const p of props.planPositions ?? []) {
    if (p.kind === 'planned_item') {
      const arr = plannedItemRows.get(p.category_id) ?? []
      arr.push(p)
      plannedItemRows.set(p.category_id, arr)
      continue
    }
    map.set(p.category_id, p)
  }
  // planNoteFor читает РОВНО budget = plan.plan_manual ?? plan.planned_amount и
  // residual = plan.ordered_residual ?? plan.residual. У 'planned_item' нет ни
  // plan_manual, ни ordered_residual (формула v2 считается только для
  // 'plan_position'/'feo_article', см. useFeoPlannedResiduals.ts), поэтому ??
  // корректно уходит на сырые Σ planned_amount / Σ residual ниже.
  for (const [categoryId, rows] of plannedItemRows) {
    if (map.has(categoryId)) continue
    const plannedQty = rows.reduce((s, r) => s + (r.planned_quantity ?? 0), 0)
    const plannedAmount = rows.reduce((s, r) => s + (r.planned_amount ?? 0), 0)
    const consumed = rows.reduce((s, r) => s + (r.consumed ?? 0), 0)
    const consumedQty = rows.reduce((s, r) => s + (r.consumed_quantity ?? 0), 0)
    const residual = rows.reduce((s, r) => s + (r.residual ?? 0), 0)
    const residualQty = rows.reduce((s, r) => s + (r.residual_quantity ?? 0), 0)
    map.set(categoryId, {
      id: categoryId,
      name: rows[0].name,
      path: rows[0].path,
      category_id: categoryId,
      kind: 'plan_position',
      planned_quantity: plannedQty > 0 ? plannedQty : null,
      unit: rows[0].unit,
      planned_amount: plannedAmount,
      unit_price: plannedQty > 0 ? plannedAmount / plannedQty : null,
      consumed,
      consumed_quantity: consumedQty,
      residual,
      residual_quantity: residualQty,
      key: `plan_position:${categoryId}`,
    })
  }
  return map
})

// Имена с обрезанными пробелами — считаем один раз здесь, а не в каждом месте
// использования (путь, отображение в дереве, поиск, подсветка совпадений).
// В реальных данных встречаются узлы с ведущими/хвостовыми пробелами в name,
// из-за чего путь и подсветка «съезжали».
const nameById = computed((): Map<number, string> => {
  const map = new Map<number, string>()
  for (const n of props.nodes) map.set(n.id, n.name.trim())
  return map
})

// Полный путь по parent_id вверх, мемоизированный за один проход по всем узлам.
const pathById = computed((): Map<number, string> => {
  const map = new Map<number, string>()
  function resolve(id: number): string {
    const cached = map.get(id)
    if (cached !== undefined) return cached
    const node = nodeById.value.get(id)
    if (!node) return ''
    const name = nameById.value.get(id) ?? node.name.trim()
    const path = node.parent_id != null ? `${resolve(node.parent_id)} › ${name}` : name
    map.set(id, path)
    return path
  }
  for (const n of props.nodes) resolve(n.id)
  return map
})

// Цепочка id от корня до узла (используется для авто-раскрытия при открытии меню)
function buildChainFor(id: number): number[] {
  const result: number[] = []
  let cur: FeoNode | undefined = nodeById.value.get(id)
  while (cur) {
    result.push(cur.id)
    cur = cur.parent_id != null ? nodeById.value.get(cur.parent_id) : undefined
  }
  return result.reverse()
}

// ─── Выбранный узел / путь / остаток ────────────────────────────────────────
const selectedPath = computed(() =>
  props.modelValue != null ? (pathById.value.get(props.modelValue) ?? '') : ''
)

const isLeafSelected = computed((): boolean => {
  if (props.modelValue == null) return false
  return nodeById.value.get(props.modelValue)?.is_leaf ?? false
})

// Подпись «План/Ост.» для узла: сперва пробуем leaves (budget/residual из FeoLeaf —
// считается ИСКЛЮЧИТЕЛЬНО от FeoCategory.budget/feo_amount), и если там пусто —
// фолбэк на плановую позицию из planPositions (план из planned_quantity ×
// planned_amount, см. planByCategory выше). Без planPositions — прежнее поведение.
function planNoteFor(nodeId: number): { budget: number | null; residual: number | null } | null {
  const leaf = leafById.value.get(nodeId)
  if (leaf && leaf.budget) {
    return { budget: leaf.budget, residual: leaf.residual }
  }
  const plan = planByCategory.value.get(nodeId)
  if (plan) {
    return {
      budget: plan.plan_manual ?? plan.planned_amount,
      residual: plan.ordered_residual ?? plan.residual,
    }
  }
  if (leaf) return { budget: leaf.budget, residual: leaf.residual }
  return null
}

// ─── Остаток по КАЖДОМУ узлу (задача владельца 2026-08-06) ──────────────────
// Гейт на праве проверяется здесь ЖЕ (belt-and-braces поверх бэкенда, который
// и так возвращает budget/free=null без права feo_budget.view_tree_amounts) —
// эффективные actions уже загружены authStore при старте сессии.
const authStore = useAuthStore()
const showNodeAmounts = computed(() => authStore.hasAction('feo_budget.view_tree_amounts'))

function nodeAmountDisplayFor(nodeId: number): { budget: number; free: number } | null {
  if (!showNodeAmounts.value || !props.nodeAmounts) return null
  return props.nodeAmounts[nodeId] ?? null
}

// Поле остатка на листе — то же, что берёт FeoCascadeSelect (budget/residual из FeoLeaf),
// с фолбэком на планPositions (см. planNoteFor).
const selectedLeafForNote = computed((): { budget: number | null; residual: number | null } | null => {
  if (!isLeafSelected.value || props.modelValue == null) return null
  return planNoteFor(props.modelValue)
})

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽'
}

// ─── Подсветка совпадений поиска ────────────────────────────────────────────
function highlightParts(name: string, q: string): { text: string; hit: boolean }[] {
  const idx = name.toLowerCase().indexOf(q)
  if (idx === -1) return [{ text: name, hit: false }]
  const parts: { text: string; hit: boolean }[] = []
  if (idx > 0) parts.push({ text: name.slice(0, idx), hit: false })
  parts.push({ text: name.slice(idx, idx + q.length), hit: true })
  if (idx + q.length < name.length) parts.push({ text: name.slice(idx + q.length), hit: false })
  return parts
}

// ─── Плоский список видимых строк дерева ────────────────────────────────────
// Помимо depth/pseudo каждая строка несёт isLast (последняя ли она среди
// видимых соседей) и ancestorLines (для каждого уровня предка — нужна ли
// вертикальная направляющая, т.е. есть ли у этого предка ещё соседи ниже).
// Это считается здесь, один раз при построении списка, а не в шаблоне.
interface FlatItem {
  key: string
  depth: number
  pseudo: boolean
  root?: boolean
  isLast: boolean
  ancestorLines: boolean[]
  parentId?: number | null
  node?: FeoNode
  name?: string
  parts?: { text: string; hit: boolean }[]
}

const flatTree = computed((): FlatItem[] => {
  const q = searchQuery.value.trim().toLowerCase()
  const roots = childrenByParent.value.get(null) ?? []
  // Если есть ствол — реальные узлы уровня 1 сдвигаются на +1 в глубину.
  const baseDepth = hasRoot.value ? 1 : 0

  if (q) {
    // Режим поиска: показываем совпавшие узлы + все их предки (виден весь путь),
    // ветки к совпадениям раскрываются автоматически. Псевдо-«Не определена» скрыт.
    // Ствол — предок всего, поэтому показываем его тоже, если есть хоть один результат.
    const result: FlatItem[] = []
    const matched = new Set<number>()
    for (const n of props.nodes) if ((nameById.value.get(n.id) ?? '').toLowerCase().includes(q)) matched.add(n.id)
    const ancestors = new Set<number>()
    for (const id of matched) {
      const chain = buildChainFor(id)
      for (const aid of chain.slice(0, -1)) ancestors.add(aid)
    }
    const visible = (n: FeoNode) => matched.has(n.id) || ancestors.has(n.id)

    const walk = (list: FeoNode[], depth: number, ancestorLines: boolean[]) => {
      const siblings = list.filter(visible)
      siblings.forEach((node, idx) => {
        const isLast = idx === siblings.length - 1
        const isMatch = matched.has(node.id)
        const name = nameById.value.get(node.id) ?? node.name.trim()
        result.push({
          key: `n-${node.id}`,
          depth,
          pseudo: false,
          node,
          name,
          parts: isMatch ? highlightParts(name, q) : undefined,
          isLast,
          ancestorLines,
        })
        const children = childrenByParent.value.get(node.id)
        if (children && children.length) walk(children, depth + 1, [...ancestorLines, !isLast])
      })
    }
    walk(roots, baseDepth, [])

    if (result.length && hasRoot.value) {
      result.unshift({
        key: 'root',
        depth: 0,
        pseudo: false,
        root: true,
        isLast: true,
        ancestorLines: [],
        name: props.rootLabel ?? '',
      })
    }
    return result
  }

  // Обычный режим: раскрытие управляется состоянием expanded/rootExpanded.
  const result: FlatItem[] = []

  function walkChildren(list: FeoNode[], depth: number, ancestorLines: boolean[], pseudoParentId: number | null | undefined) {
    // pseudoParentId !== undefined означает «для этого списка нужно добавить
    // хвостовой псевдо-узел „Не определена“» (если allowUnallocated включён).
    const hasPseudo = pseudoParentId !== undefined && !!props.allowUnallocated && !props.readonly
    list.forEach((node, idx) => {
      const isLast = idx === list.length - 1 && !hasPseudo
      const name = nameById.value.get(node.id) ?? node.name.trim()
      result.push({ key: `n-${node.id}`, depth, pseudo: false, node, name, isLast, ancestorLines })
      if (!node.is_leaf && expanded.value.has(node.id)) {
        const children = childrenByParent.value.get(node.id) ?? []
        walkChildren(children, depth + 1, [...ancestorLines, !isLast], node.id)
      }
    })
    if (hasPseudo) {
      result.push({ key: `u-${pseudoParentId}`, depth, pseudo: true, parentId: pseudoParentId, isLast: true, ancestorLines })
    }
  }

  if (hasRoot.value) {
    result.push({ key: 'root', depth: 0, pseudo: false, root: true, isLast: true, ancestorLines: [], name: props.rootLabel ?? '' })
    if (!rootExpanded.value) return result
  }
  walkChildren(roots, baseDepth, [], null)
  return result
})

// ─── Действия ────────────────────────────────────────────────────────────────
function toggleExpand(id: number) {
  const s = new Set(expanded.value)
  s.has(id) ? s.delete(id) : s.add(id)
  expanded.value = s
}

function toggleRootExpand() {
  rootExpanded.value = !rootExpanded.value
}

function expandAllNodes() {
  const s = new Set<number>()
  for (const n of props.nodes) if (!n.is_leaf) s.add(n.id)
  expanded.value = s
  rootExpanded.value = true
}

function collapseAllNodes() {
  expanded.value = new Set()
  rootExpanded.value = false
}

function onNodeClick(node: FeoNode) {
  // Эмитим id ЛЮБОГО кликнутого узла (лист или папка) — от этого зависит
  // массовая пропагация уровня в PurchaseItemsEditor.onItemFeoChange.
  emit('update:modelValue', node.id)
  if (node.is_leaf) {
    menuOpen.value = false
  } else {
    // Папка — валидный промежуточный выбор; раскрываем её и оставляем меню открытым.
    const s = new Set(expanded.value)
    s.add(node.id)
    expanded.value = s
  }
}

function onPickUnallocated(parentId: number | null) {
  emit('pick-unallocated', parentId)
  menuOpen.value = false
}

function onClear(e: MouseEvent) {
  e.stopPropagation()
  emit('update:modelValue', null)
}

// ─── Открытие меню: сброс поиска, раскрытие ВСЕХ узлов, скролл к выбранному ──
function updateMenuWidth() {
  if (fieldWrapEl.value) menuMinWidth.value = Math.max(fieldWrapEl.value.offsetWidth, 280)
  menuMaxWidth.value = Math.min(720, Math.round(window.innerWidth * 0.92))
}

function scrollToSelected() {
  if (props.modelValue == null || !treeScrollEl.value) return
  const el = treeScrollEl.value.querySelector(`[data-node-id="${props.modelValue}"]`) as HTMLElement | null
  el?.scrollIntoView({ block: 'center' })
}

// ─── Ручной auto-grow для поля (см. докстринг у v-textarea выше) ───────────────
// Встроенный auto-grow Vuetify считает высоту неверно в глубоко вложенном/анимированном
// контексте (expand-row таблицы позиций закупки) — остаётся на высоте одной строки,
// путь обрезается внутренним скроллом. Меряем и выставляем высоту сами: это не зависит
// от того, где и как смонтирован компонент.
function resizeFeoTextarea() {
  // fieldWrapEl — обычный DOM-ref на оборачивающий div (уже используется в
  // updateMenuWidth), а не ref на сам компонент v-textarea: ref прямо на
  // <v-textarea v-bind="activatorProps"> не долетает до значения (компилятор
  // мёржит проп ref через _mergeProps и теряет спец-обработку для <script setup>,
  // проверено экспериментально). Обёртка ни с чем не мёржится — её ref рабочий.
  const ta = fieldWrapEl.value?.querySelector?.('textarea') as HTMLTextAreaElement | null | undefined
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = `${ta.scrollHeight}px`
}

let fieldResizeObserver: ResizeObserver | null = null

onMounted(() => {
  // Первичная высота — после отрисовки label/border (nextTick), и повторно на
  // следующем тике на случай, если шрифт/иконки ещё не подгрузились к первому замеру.
  nextTick(resizeFeoTextarea)
  requestAnimationFrame(resizeFeoTextarea)
  // Ширина поля меняется НЕ только при маунте: разворачивание строки таблицы (transition),
  // изменение ширины колонки, ресайз окна — во всех случаях перенос текста может измениться,
  // и высоту нужно пересчитать заново.
  if (fieldWrapEl.value && typeof ResizeObserver !== 'undefined') {
    fieldResizeObserver = new ResizeObserver(() => resizeFeoTextarea())
    fieldResizeObserver.observe(fieldWrapEl.value)
  }
})

onBeforeUnmount(() => {
  fieldResizeObserver?.disconnect()
  fieldResizeObserver = null
})

// Текст поля меняется при выборе другого узла ФЭО — пересчитываем высоту.
watch(selectedPath, () => nextTick(resizeFeoTextarea))

watch(menuOpen, (open) => {
  if (!open) return
  searchQuery.value = ''
  // Пользователь явно просил: при каждом открытии дерево полностью развёрнуто
  // (а не только путь к выбранному узлу), состояние сбрасывается заново.
  expandAllNodes()
  nextTick(() => {
    updateMenuWidth()
    searchInputEl.value?.focus?.()
    scrollToSelected()
  })
})
</script>

<style scoped>
.feo-tree-select {
  display: flex;
  flex-direction: column;
}

.feo-tree-field {
  cursor: pointer;
}
.feo-tree-field--readonly {
  cursor: default;
  opacity: 0.85;
}
.feo-tree-select :deep(.v-field__input) {
  font-size: 12px !important;
}
.feo-tree-select :deep(.v-field__field) {
  font-size: 12px;
}
.feo-tree-select :deep(.feo-tree-field textarea) {
  cursor: pointer;
  /* Высоту считаем и выставляем сами (см. resizeFeoTextarea) — здесь только
     гарантируем, что при любой рассинхронизации замера НЕ появится внутренний
     скролл/обрезка, а перенос идёт по словам, а не обрезкой символа. */
  overflow-y: hidden;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}
/* Многострочное значение растёт вниз — крестик очистки и каретку держим
   у ПЕРВОЙ строки (flex-start), иначе они уедут в вертикальный центр поля. */
.feo-tree-select :deep(.feo-tree-field .v-field) {
  align-items: flex-start;
}
.feo-tree-select :deep(.feo-tree-field .v-field__append-inner) {
  padding-top: 6px;
}
.feo-tree-caret {
  transition: transform 0.15s;
  color: var(--crm-text-faint);
}
.feo-tree-caret--open {
  transform: rotate(180deg);
}
.feo-tree-clear {
  color: var(--crm-text-faint);
  margin-right: 2px;
}
.feo-tree-clear:hover {
  color: var(--crm-text-secondary);
}

.feo-tree-note {
  line-height: 1.3;
}

/* ── Меню-карточка дерева ── */
.feo-tree-menu-card {
  background: var(--crm-surface);
  color: var(--crm-text);
  display: flex;
  flex-direction: column;
  max-height: 60vh;
}
.feo-tree-search {
  border-bottom: 1px solid var(--crm-border);
  flex-shrink: 0;
}
.feo-tree-scroll {
  /* Раньше сюда пытались растянуть высоту через flex:1 1 auto, но родитель
     (.feo-tree-menu-card) не имеет собственной ЗАДАННОЙ высоты (только
     max-height), поэтому flex-grow не получает свободного места и контейнер
     схлопывается почти в 0 — дерево рисуется, но видна только строка поиска.
     Фикс: задаём контейнеру дерева СОБСТВЕННУЮ ограниченную высоту, не
     зависящую от растяжения флексом. При малом числе узлов высота — по
     содержимому (без искусственных пустот), при большом — скролл. */
  overflow-y: auto;
  max-height: min(52vh, 420px);
}

.feo-tree-row {
  --feo-row-line: 28px;
  display: flex;
  /* flex-start, не center: длинные названия переносятся на несколько строк
     (см. .feo-tree-name), и «уголок»/иконка должны остаться у ПЕРВОЙ строки,
     а не уехать в центр всего многострочного блока. */
  align-items: flex-start;
  min-height: var(--feo-row-line);
  padding: 0 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--crm-text);
  gap: 2px;
}
.feo-tree-row:hover {
  background: var(--crm-surface-alt);
}
.feo-tree-row--selected {
  background: rgba(59, 130, 246, 0.12);
  font-weight: 600;
}
.feo-tree-row--pseudo {
  color: var(--crm-text-muted);
  font-style: italic;
}
.feo-tree-row--root {
  font-weight: 700;
}

/* ── Направляющие линии «настоящего дерева» ──
   Рисуются спейсерами с border/psevdo-элементами, не текстовыми символами,
   чтобы не ломались при переносе текста в многострочном поле/строке. */
.feo-tree-rail,
.feo-tree-elbow {
  position: relative;
  width: 18px;
  align-self: stretch;
  flex-shrink: 0;
}
.feo-tree-rail--line::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--crm-border);
}
.feo-tree-elbow::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 0;
  /* Высота — половина ОДНОЙ строки (не 50% всей, потенциально многострочной,
     ячейки), чтобы горизонтальный стык уголка совпадал с первой строкой текста. */
  height: calc(var(--feo-row-line) / 2);
  width: 1px;
  background: var(--crm-border);
}
.feo-tree-elbow::after {
  content: '';
  position: absolute;
  left: 8px;
  top: calc(var(--feo-row-line) / 2);
  height: 1px;
  width: 10px;
  background: var(--crm-border);
}
/* Узел не последний среди соседей — вертикаль продолжается на всю высоту
   строки (включая перенесённые строки текста), а не только до середины. */
.feo-tree-elbow--open::before {
  height: 100%;
}

.feo-tree-chevron {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
/* Шеврон и иконка узла — на уровне первой строки текста (row теперь
   align-items:flex-start), небольшой отступ сверху для оптического центра. */
.feo-tree-chevron,
.feo-tree-row-icon {
  margin-top: calc((var(--feo-row-line) - 16px) / 2);
}
.feo-tree-name {
  /* Полный перенос вместо обрезки многоточием — пользователь явно просил
     не прятать текст названий категорий, как раньше прятался путь в поле. */
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  flex: 1 1 auto;
  min-width: 0;
}
.feo-tree-name--pseudo {
  font-style: italic;
}
.feo-tree-name--root {
  font-weight: 700;
}
.feo-tree-hit {
  background: rgba(251, 146, 60, 0.35);
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}
.feo-tree-desc {
  color: var(--crm-text-faint);
  font-size: 11px;
  margin-left: 6px;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  flex-shrink: 1;
  min-width: 0;
}
.feo-tree-residual {
  margin-left: auto;
  padding-left: 10px;
  flex-shrink: 0;
  font-size: 11px;
  color: var(--crm-text-muted);
  white-space: nowrap;
}
.feo-tree-residual--negative {
  color: #DC2626;
  font-weight: 600;
}

/* Компактный режим для строк таблицы */
.feo-tree-select.is-horizontal .feo-tree-row {
  --feo-row-line: 24px;
  font-size: 12px;
  min-height: var(--feo-row-line);
}
.feo-tree-select.is-horizontal .feo-tree-rail,
.feo-tree-select.is-horizontal .feo-tree-elbow {
  width: 14px;
}
.feo-tree-select.is-horizontal .feo-tree-rail--line::before,
.feo-tree-select.is-horizontal .feo-tree-elbow::before {
  left: 6px;
}
.feo-tree-select.is-horizontal .feo-tree-elbow::after {
  left: 6px;
  width: 8px;
}
</style>
