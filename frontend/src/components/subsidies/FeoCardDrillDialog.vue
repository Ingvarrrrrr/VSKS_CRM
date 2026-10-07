<!-- Задача 2 (владелец, 07.10.2026, план .planning/quick/2026-10-07-dnr-feo-
     cards/PLAN.md): «из чего сложено» число карточек «Бюджет (ФЭО)» /
     «Запланировано» / «Свободно» на карточке субсидии — GET /api/subsidies/
     {id}/card-drill (backend/app/services/feo_card_drill.py, ПРАВИЛО №6: одна
     формула у карточки SubsidyKpiCards.vue и у этого окна, сама Σ строк ==
     total == числу карточки по построению, см. докстринг модуля). Новый файл
     (Правило №5 — не дописывается в SubsidyKpiCards.vue/StageFeoDrillDialog.vue/
     RedistributableDrillDialog.vue, по образцу последних — тот же api-клиент,
     describeApiError, индикатор загрузки, formatCurrency, см. их докстринги).

     Переключатель «товар/услуга» — ТОЛЬКО для строк kind='unspecified' режима
     card='planned' — переиспользует ЕДИНСТВЕННЫЙ «сеттер» плановой позиции
     (useFeoLevel5ItemType.ts::saveInlineItemType → putPlannedItemFull →
     PUT /feo-planned-items/{id}, Правило №6, второй механизм записи
     item_type здесь не заводится). Строка card-drill несёт только часть полей
     FeoPlannedItem (нужны для РАЗЛОЖЕНИЯ по статьям/типам, не для полной
     замены) — полный объект (нужен PUT'у, который заменяет позицию целиком)
     догружается ПЕРЕД записью через GET /feo-planned-items/?feo_category_id=
     (существующая ручка списка позиций категории, backend не трогаем). -->
<template>
  <v-dialog :model-value="visible" max-width="1100" scrollable :fullscreen="mobile"
    @update:model-value="v => !v && emit('close')">
    <v-card>
      <v-card-title class="d-flex align-center pa-4"
        style="background: linear-gradient(90deg, #92400e, #7c2d12); color: white;">
        <div style="flex:1; min-width:0">
          <div class="text-h6 font-weight-bold" style="line-height:1.2">{{ title }}</div>
        </div>
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
          <!-- card='planned' — построчно по плановым позициям -->
          <v-table v-if="card === 'planned'" density="compact" style="min-width:900px">
            <thead>
              <tr>
                <th class="px-4">Направление ФЭО</th>
                <th class="px-4">Позиция</th>
                <th class="px-4">Тип</th>
                <th class="text-right px-4">Кол-во</th>
                <th class="text-right px-4">Сумма</th>
                <th v-if="kind === 'all' || kind === 'unspecified'" class="px-4">Сменить тип</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, idx) in plannedRows" :key="(r.planned_item_id ?? 'cat') + '-' + idx">
                <td class="px-4 text-caption category-path-cell" :title="r.category_path">{{ lastSegment(r.category_path) }}</td>
                <td class="px-4 py-2" style="max-width:260px; white-space:normal; font-size:13px">{{ r.name || '—' }}</td>
                <td class="px-4 text-caption">{{ r.kind_label }}</td>
                <td class="text-right px-4 text-caption">{{ r.quantity ?? '—' }}</td>
                <td class="text-right px-4 font-weight-medium text-primary">{{ formatCurrency(r.amount) }}</td>
                <td v-if="kind === 'all' || kind === 'unspecified'" class="px-4">
                  <v-btn-toggle v-if="r.kind === 'unspecified' && r.planned_item_id" density="compact" variant="outlined" divided>
                    <v-btn size="x-small" :loading="togglingId === r.planned_item_id" @click="saveItemType(r, 'товар')">Товар</v-btn>
                    <v-btn size="x-small" :loading="togglingId === r.planned_item_id" @click="saveItemType(r, 'услуга')">Услуга</v-btn>
                  </v-btn-toggle>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td :colspan="(kind === 'all' || kind === 'unspecified') ? 4 : 4" class="px-4 text-right font-weight-medium">Итого:</td>
                <td class="text-right px-4 font-weight-bold text-primary">{{ formatCurrency(total) }}</td>
                <td v-if="kind === 'all' || kind === 'unspecified'" />
              </tr>
            </tfoot>
          </v-table>

          <!-- card='budget'/'free' — построчно по статьям -->
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
const rows = ref<(BudgetFreeRow | PlannedRow)[]>([])
const total = ref(0)
const reason = ref<string | null>(null)

const plannedRows = computed(() => rows.value as PlannedRow[])
const categoryRows = computed(() => rows.value as BudgetFreeRow[])

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
    const res = await apiFetch<{ total: number; rows: (BudgetFreeRow | PlannedRow)[]; reason: string | null }>(
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

watch(() => [props.visible, props.subsidyId, props.card, props.kind], () => { if (props.visible) load() }, { immediate: true })

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
</style>
