<!-- Задача 2 (владелец, 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-
     cards/PLAN.md): «из чего сложено» число карточек «Бюджет (ФЭО)» /
     «Запланировано» / «Свободно» на карточке субсидии — GET /api/subsidies/
     {id}/card-drill (backend/app/services/feo_card_drill.py, ПРАВИЛО №6: одна
     формула у карточки SubsidyKpiCards.vue и у этого окна, сама Σ строк ==
     total == числу карточки по построению, см. докстринг модуля). Новый файл
     (Правило №5 — не дописывается в SubsidyKpiCards.vue/StageFeoDrillDialog.vue/
     RedistributableDrillDialog.vue, по образцу последних — тот же api-клиент,
     describeApiError, индикатор загрузки, formatCurrency, см. их докстринги).

     Переключатель «товар/услуга» — для ЛЮБОЙ строки card='planned' с
     planned_item_id (правка владельца 07.10.2026, п.1 — раньше был только у
     kind='unspecified'; текущий тип теперь отмечен цветом кнопки) —
     переиспользует ЕДИНСТВЕННЫЙ «сеттер» плановой позиции (useFeoLevel5ItemType.ts
     ::saveInlineItemType → putPlannedItemFull → PUT /feo-planned-items/{id},
     Правило №6, второй механизм записи item_type здесь не заводится). Строка
     card-drill несёт только часть полей FeoPlannedItem (нужны для РАЗЛОЖЕНИЯ
     по статьям/типам, не для полной замены) — полный объект (нужен PUT'у,
     который заменяет позицию целиком) догружается ПЕРЕД записью через GET
     /feo-planned-items/?feo_category_id= (существующая ручка списка позиций
     категории, backend не трогаем).

     card='planned' — дерево по категориям ФЭО (правка владельца 07.10.2026,
     п.2) — строится НА ФРОНТЕ из category_path, который строка уже несёт
     (backend не трогаем второй раз, ПРАВИЛО №6: один источник пути — _category_path
     в feo_card_drill.py). buildFolderTree() ниже группирует построчно по
     сегментам пути на каждой глубине — папка несёт И своих прямых детей-папки
     (сегмент длиннее), И свои прямые позиции (сегмент заканчивается на ней),
     одновременно (тот же случай «Чайник+Термопот на статье с подкатегорией»,
     test_budget_card_chainik_termopot_regression). Итог/количество папки —
     Σ/count ВСЕХ вложенных позиций рекурсивно — Σ корневых папок == total
     окна == карточке (строки не пересчитывались, просто перегруппированы).
     expanded — Set развёрнутых ключей узлов, по умолчанию только 1-й уровень
     (корни категорий) — см. watch ниже, который инициализирует его после load().

     card='free' с kind ≠ 'all' — строки по НАПРАВЛЕНИЮ, не по статьям (правка
     владельца 07.10.2026, п.3) — backend теперь отдаёт budget_amount/
     planned_amount/items прямо на корне (см. feo_card_drill.py), это окно
     просто их отображает, Σ amount по направлениям == total == карточке
     «Свободно» по этому типу (тот же ряд, что splitRowsFor('free') в
     SubsidyKpiCards.vue — не трогаем файл, сверяем числом). items — позиции
     плана этого направления/типа, отданные backend'ом уже created_at DESC
     (последние добавленные первыми) — показываются раскрывающимся списком
     под строкой превышения. -->
<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #92400e, #7c2d12); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">{{ title }}</div>
        </div>
        <v-btn v-if="card === 'planned' && rows.length"
          size="small" variant="tonal" color="white" class="mr-2"
          @click="allExpanded ? collapseAll() : expandAll()">
          {{ allExpanded ? 'Свернуть всё' : 'Развернуть всё' }}
        </v-btn>
        <v-chip size="small" variant="tonal" class="mr-2" color="white">{{ rows.length }} {{ rowsWord }}</v-chip>
        <v-btn icon="mdi-close" variant="text" color="white" @click="emit('close')" />
      </v-card-title>

      <v-card-text class="pa-0" style="max-height:65vh; overflow-y:auto">
        <div v-if="loading" class="text-center py-12">
          <v-progress-linear indeterminate color="primary" class="mb-4" />
          <div class="text-caption text-medium-emphasis">загрузка расшифровки…</div>
        </div>
        <v-alert v-else-if="rows.length === 0" type="info" variant="tonal" density="compact" class="ma-3">
          {{ reason || 'Нет данных' }}
        </v-alert>
        <div v-else style="overflow-x:auto">
          <!-- card='planned' — дерево категорий ФЭО → позиции (см. докстринг выше) -->
          <v-table v-if="card === 'planned'" density="compact" style="min-width:900px">
            <thead>
              <tr>
                <th class="px-4">Направление ФЭО / позиция</th>
                <th class="px-4">Тип</th>
                <th class="text-right px-4">Кол-во</th>
                <th class="text-right px-4">Сумма</th>
                <th class="px-4">Сменить тип</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="frow in flatPlannedRows" :key="frow.key">
                <tr v-if="frow.type === 'folder'" class="feo-drill-folder-row" @click="toggleFolder(frow.node.key)">
                  <td class="px-4 py-2" :style="{ paddingLeft: (16 + frow.depth * 20) + 'px' }">
                    <v-icon size="18" class="mr-1">{{ expanded.has(frow.node.key) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                    <span class="font-weight-medium" :title="frow.node.key">{{ frow.node.name }}</span>
                    <span class="text-caption text-medium-emphasis ml-2">{{ frow.node.count }} {{ pluralizeRows(frow.node.count) }}</span>
                  </td>
                  <td class="px-4" />
                  <td class="text-right px-4" />
                  <td class="text-right px-4 font-weight-medium text-primary">{{ formatCurrency(frow.node.amount) }}</td>
                  <td class="px-4" />
                </tr>
                <tr v-else>
                  <td class="px-4 py-2" :style="{ paddingLeft: (16 + frow.depth * 20) + 'px', maxWidth: '280px', whiteSpace: 'normal', fontSize: '13px' }">
                    {{ frow.row.name || '—' }}
                  </td>
                  <td class="px-4 text-caption">{{ frow.row.kind_label }}</td>
                  <td class="text-right px-4 text-caption">{{ frow.row.quantity ?? '—' }}</td>
                  <td class="text-right px-4 font-weight-medium text-primary">{{ formatCurrency(frow.row.amount) }}</td>
                  <td class="px-4">
                    <v-btn-toggle v-if="frow.row.planned_item_id" density="compact" variant="outlined" divided>
                      <v-btn size="x-small" :color="frow.row.item_type === 'товар' ? 'primary' : undefined"
                        :loading="togglingId === frow.row.planned_item_id" @click.stop="saveItemType(frow.row, 'товар')">Товар</v-btn>
                      <v-btn size="x-small" :color="frow.row.item_type === 'услуга' ? 'primary' : undefined"
                        :loading="togglingId === frow.row.planned_item_id" @click.stop="saveItemType(frow.row, 'услуга')">Услуга</v-btn>
                    </v-btn-toggle>
                  </td>
                </tr>
              </template>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="3" class="px-4 text-right font-weight-medium">Итого:</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(total) }}</td>
                <td class="px-4" />
              </tr>
            </tfoot>
          </v-table>

          <!-- card='free' с конкретной корзиной — по НАПРАВЛЕНИЯМ, с раскрытием
               позиций у превышения (см. докстринг выше) -->
          <v-table v-else-if="card === 'free' && kind !== 'all'" density="compact" style="min-width:820px">
            <thead>
              <tr>
                <th class="px-4">Направление ФЭО</th>
                <th class="text-right px-4">Бюджет ФЭО ({{ kindTitle }})</th>
                <th class="text-right px-4">Запланировано ({{ kindTitle }})</th>
                <th class="text-right px-4">Свободно / Превышение</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="r in directionRows" :key="r.feo_category_id ?? 'manual'">
                <tr :class="{ 'feo-drill-folder-row': r.amount < -0.5 && r.items.length }"
                  @click="r.amount < -0.5 && r.items.length ? toggleFolder('dir-' + r.feo_category_id) : null">
                  <td class="px-4 py-2">
                    <v-icon v-if="r.amount < -0.5 && r.items.length" size="18" class="mr-1">
                      {{ expanded.has('dir-' + r.feo_category_id) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
                    </v-icon>
                    <span class="font-weight-medium">{{ r.category_path || '—' }}</span>
                  </td>
                  <td class="text-right px-4">{{ formatCurrency(r.budget_amount) }}</td>
                  <td class="text-right px-4">{{ formatCurrency(r.planned_amount) }}</td>
                  <td class="text-right px-4 font-weight-medium" :class="r.amount < -0.5 ? 'text-error' : 'text-primary'">
                    {{ r.amount < -0.5 ? 'превышение ' : 'свободно ' }}{{ formatCurrency(Math.abs(r.amount)) }}
                  </td>
                </tr>
                <template v-if="r.amount < -0.5 && r.items.length && expanded.has('dir-' + r.feo_category_id)">
                  <tr v-for="it in r.items" :key="'item-' + it.planned_item_id">
                    <td class="px-4 py-1 text-caption" style="padding-left:40px; max-width:320px; white-space:normal">{{ it.name || '—' }}</td>
                    <td class="px-4" />
                    <td class="text-right px-4 text-caption">{{ formatCurrency(it.amount) }}</td>
                    <td class="px-4 text-caption text-medium-emphasis">{{ formatDate(it.created_at) }}</td>
                  </tr>
                </template>
              </template>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="3" class="px-4 text-right font-weight-medium">Итого:</td>
                <td class="text-right px-4 font-weight-bold" :class="total < -0.5 ? 'text-error' : 'text-primary'">
                  {{ total < -0.5 ? 'превышение ' : 'свободно ' }}{{ formatCurrency(Math.abs(total)) }}
                </td>
              </tr>
            </tfoot>
          </v-table>

          <!-- card='budget' либо card='free' с kind='all' — построчно по статьям -->
          <v-table v-else density="compact" style="min-width:700px">
            <thead>
              <tr>
                <th class="px-4">Направление ФЭО</th>
                <th class="px-4">Тип</th>
                <th class="text-right px-4">Сумма</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, idx) in categoryRows" :key="(r.feo_category_id ?? 'manual') + '-' + idx">
                <td class="px-4 text-caption category-path-cell" :title="r.category_path">{{ lastSegment(r.category_path) || '—' }}</td>
                <td class="px-4 text-caption">{{ r.kind_label }}</td>
                <td class="text-right px-4 font-weight-medium" :class="r.amount < -0.5 ? 'text-error' : 'text-primary'">
                  {{ formatCurrency(r.amount) }}
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="2" class="px-4 text-right font-weight-medium">Итого:</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(total) }}</td>
              </tr>
            </tfoot>
          </v-table>
        </div>
      </v-card-text>

      <v-card-actions class="px-5 pb-4">
        <v-spacer />
        <v-btn @click="emit('close')">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import { apiFetch } from '@/api'
import { describeApiError } from '@/utils/apiErrorMessage'
import { useToast } from '@/composables/useToast'
import { formatCurrency } from '@/composables/subsidies/format'
import { KIND_LABELS, type ItemTypeKind } from '@/utils/itemTypeKind'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { useFeoLevel5ItemType } from '@/composables/subsidies/useFeoLevel5ItemType'
import type { FeoPlannedItem } from '@/composables/subsidies/types'

const { mobile } = useDisplay()
const toast = useToast()

export type FeoCardDrillCard = 'budget' | 'planned' | 'free'

interface BudgetFreeRow {
  feo_category_id: number | null
  category_path: string
  kind: ItemTypeKind
  kind_label: string
  amount: number
}
interface PlannedRow extends BudgetFreeRow {
  planned_item_id: number | null
  name: string | null
  item_type: string | null
  quantity: number | null
}
interface DirectionItem {
  planned_item_id: number
  name: string | null
  amount: number
  created_at: string | null
}
interface DirectionRow extends BudgetFreeRow {
  budget_amount: number
  planned_amount: number
  items: DirectionItem[]
}

const props = defineProps<{
  visible: boolean
  subsidyId: number | null
  card: FeoCardDrillCard
  kind: ItemTypeKind | 'all'
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

// ctx — тот же singleton, что построен SubsidiesView.vue (useSubsidyDetailCtx()
// без аргумента переиспользует уже собранный контекст, тот же приём, что у
// useFeoTreeExcess()/useExcessDrilldown() в SubsidyKpiCards.vue) — нужен
// useFeoLevel5ItemType(ctx) для безопасной записи item_type (Правило №6).
const ctx = useSubsidyDetailCtx()
const itemTypeInline = useFeoLevel5ItemType(ctx)
const togglingId = ref<number | null>(null)

const loading = ref(false)
const rows = ref<(BudgetFreeRow | PlannedRow | DirectionRow)[]>([])
const total = ref(0)
const reason = ref<string | null>(null)

const plannedRows = computed(() => rows.value as PlannedRow[])
const categoryRows = computed(() => rows.value as BudgetFreeRow[])
const directionRows = computed(() => rows.value as DirectionRow[])

function pluralizeRows(n: number): string {
  const mod100 = Math.abs(n) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return 'строк'
  if (mod10 === 1) return 'строка'
  if (mod10 >= 2 && mod10 <= 4) return 'строки'
  return 'строк'
}
const rowsWord = computed(() => pluralizeRows(rows.value.length))

const CARD_LABELS: Record<FeoCardDrillCard, string> = {
  budget: 'Бюджет (ФЭО)',
  planned: 'Запланировано',
  free: 'Свободно',
}
const kindTitle = computed(() => props.kind === 'all' ? 'всё' : KIND_LABELS[props.kind])
const title = computed(() => `${CARD_LABELS[props.card]} — ${kindTitle.value}`)

function lastSegment(path: string): string {
  if (!path) return ''
  const parts = path.split(' › ')
  return parts[parts.length - 1] || ''
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('ru-RU')
}

// ── Дерево категорий для card='planned' (правка владельца 07.10.2026, п.2) ──
// Строится из category_path, который строка УЖЕ несёт — backend не трогаем
// второй раз (ПРАВИЛО №6, см. докстринг файла наверху).
interface FolderNode {
  key: string
  name: string
  amount: number
  count: number
  children: FolderNode[]
  rows: PlannedRow[]
}

function pathSegments(path: string | null | undefined): string[] {
  return (path || '').split(' › ').map(s => s.trim()).filter(Boolean)
}

function groupByDepth(items: PlannedRow[], depth: number, parentKey: string): FolderNode[] {
  const order: string[] = []
  const byName = new Map<string, PlannedRow[]>()
  for (const r of items) {
    const segs = pathSegments(r.category_path)
    const seg = segs[depth] ?? '(без категории)'
    if (!byName.has(seg)) { byName.set(seg, []); order.push(seg) }
    byName.get(seg)!.push(r)
  }
  return order.map(name => {
    const groupRows = byName.get(name)!
    const key = parentKey + '/' + name
    const direct = groupRows.filter(r => pathSegments(r.category_path).length <= depth + 1)
    const deeper = groupRows.filter(r => pathSegments(r.category_path).length > depth + 1)
    return {
      key,
      name,
      amount: groupRows.reduce((s, r) => s + (r.amount || 0), 0),
      count: groupRows.length,
      children: deeper.length ? groupByDepth(deeper, depth + 1, key) : [],
      rows: direct,
    }
  })
}

const plannedTree = computed<FolderNode[]>(() => groupByDepth(plannedRows.value, 0, ''))

// expanded — ключи развёрнутых папок ЛЮБОЙ глубины (не только корня); по
// умолчанию, после каждой загрузки, развёрнут только 1-й уровень (владелец,
// п.2 — "по умолчанию развёрнут только первый уровень").
const expanded = ref<Set<string>>(new Set())

function toggleFolder(key: string) {
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

function allFolderKeys(nodes: FolderNode[], out: string[] = []): string[] {
  for (const n of nodes) {
    out.push(n.key)
    allFolderKeys(n.children, out)
  }
  return out
}

function expandAll() {
  expanded.value = new Set(allFolderKeys(plannedTree.value))
}
function collapseAll() {
  expanded.value = new Set()
}
const allExpanded = computed(() => {
  const all = allFolderKeys(plannedTree.value)
  return all.length > 0 && all.every(k => expanded.value.has(k))
})

type FlatPlannedRow =
  | { type: 'folder'; key: string; depth: number; node: FolderNode }
  | { type: 'leaf'; key: string; depth: number; row: PlannedRow }

function flattenTree(nodes: FolderNode[], depth: number, out: FlatPlannedRow[]) {
  for (const n of nodes) {
    out.push({ type: 'folder', key: n.key, depth, node: n })
    if (expanded.value.has(n.key)) {
      flattenTree(n.children, depth + 1, out)
      for (const r of n.rows) {
        out.push({ type: 'leaf', key: n.key + '#' + (r.planned_item_id ?? 'cat'), depth: depth + 1, row: r })
      }
    }
  }
}
const flatPlannedRows = computed<FlatPlannedRow[]>(() => {
  const out: FlatPlannedRow[] = []
  flattenTree(plannedTree.value, 0, out)
  return out
})

async function load() {
  if (!props.subsidyId) {
    rows.value = []
    total.value = 0
    reason.value = null
    return
  }
  loading.value = true
  try {
    const params = new URLSearchParams({ card: props.card, kind: props.kind })
    const res = await apiFetch<{ total: number; rows: (BudgetFreeRow | PlannedRow | DirectionRow)[]; reason: string | null }>(
      `/subsidies/${props.subsidyId}/card-drill?${params.toString()}`,
    )
    rows.value = res.rows || []
    total.value = res.total || 0
    reason.value = res.reason || null
  } catch (e: any) {
    rows.value = []
    total.value = 0
    reason.value = null
    toast.error(describeApiError(e, { fallback: 'Не удалось загрузить расшифровку карточки' }))
  } finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.subsidyId, props.card, props.kind], async () => {
  if (!props.visible) return
  await load()
  // По умолчанию развёрнут только 1-й уровень дерева (владелец, п.2).
  if (props.card === 'planned') {
    expanded.value = new Set(plannedTree.value.map(n => n.key))
  }
}, { immediate: true })

// Полный снимок плановой позиции — GET /feo-planned-items/?feo_category_id=
// (существующая ручка, backend не трогаем) нужен putPlannedItemFull (PUT —
// полная замена позиции, см. docstring buildPlannedItemFullPayload в
// useFeoLevel5.ts) — строка card-drill несёт только часть полей.
async function saveItemType(row: PlannedRow, newType: 'товар' | 'услуга') {
  if (!row.planned_item_id || row.feo_category_id == null) return
  togglingId.value = row.planned_item_id
  try {
    const list = await apiFetch<FeoPlannedItem[]>(`/feo-planned-items/?feo_category_id=${row.feo_category_id}`)
    const full = list.find(it => it.id === row.planned_item_id)
    if (!full) {
      toast.error('Плановая позиция не найдена — обновите страницу')
      return
    }
    await itemTypeInline.saveInlineItemType(full, newType)
    await load()
  } catch (e: any) {
    toast.error(describeApiError(e, { fallback: 'Не удалось изменить тип позиции' }))
  } finally {
    togglingId.value = null
  }
}
</script>

<style scoped>
.category-path-cell {
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: default;
}
.feo-drill-folder-row {
  cursor: pointer;
  background: rgba(146, 64, 14, 0.05);
}
.feo-drill-folder-row:hover {
  background: rgba(146, 64, 14, 0.1);
}
</style>
