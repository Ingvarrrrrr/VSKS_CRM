<!-- SubsidyCategoryPanel.vue — «Позиции: По категориям — вся субсидия» (задача
     владельца, 28.10.2026): весь бензоинструмент (и любая другая категория
     товара каталога) собирается ОДНИМ списком со всех статей ФЭО субсидии, а
     не только внутри одной категории ФЭО, как делает обычное дерево. Позиции
     можно отметить галочками (построчно или группой) и собрать ОДНУ заявку —
     бэкенд уже принимает позиции из разных статей ФЭО в одну заявку
     (backend/app/services/plan_to_wish.py:634, ПРАВИЛО №6, этот экран ничего
     нового здесь не делает), выбор/подтверждение — ТОТ ЖЕ usePlanToRequest.ts
     и ТОТ ЖЕ общий Set useFeoLevel5Api().selectedPlannedItemIds, что и обычное
     дерево (FeoTreeRow.vue/FeoLevel5Panel.vue) — второй механизм выбора не
     заводим.

     Источник строк — GET /feo-planned-items/comparison?subsidy_id=
     (feo_planned_items_reports.py::get_comparison, subsidy_wide-режим) — тот
     же построитель (catalog_category/catalog_product_type/item_type_effective),
     что и режим одной статьи, просто без сужения по feo_category_id.

     Группировка — buildPlannedGroupEntries (useFeoPlannedItemGroups.ts), ТА ЖЕ
     функция, что уже группирует плановые позиции внутри категории ФЭО в обычном
     дереве (feoCategoryUtils.ts::buildCategoryGroupedRows, ПРАВИЛО №6) — всегда
     режим 'category_type' (категория → вид → позиции), т.к. весь смысл этой
     панели — обзор ПО КАТЕГОРИИ ТОВАРА, не по статье ФЭО.

     Фильтр «Все/Товары/Услуги» — matchesItemTypeFilter (@/utils/itemTypeKind.ts),
     применяется ДО группировки (отфильтрованные позиции не попадают в суммы
     заголовков групп) — единственная проверка, работает и в обычном дереве
     (см. FeoLevel5Panel.vue, тот же импорт). -->
<template>
  <div class="subsidy-category-panel">
    <!-- Фильтр «Все/Товары/Услуги» — кнопка уже стоит в FeoTreeToolbar.vue
         (ctx.feoItemTypeFilter, тот же singleton feoTreePrefs), второй
         переключатель здесь не рисуем (Правило №6) — только индикатор загрузки/ошибки. -->
    <div v-if="loading || loadError" class="d-flex align-center" style="gap:8px">
      <v-progress-circular v-if="loading" indeterminate size="18" width="2" color="teal" />
      <span v-if="loadError" class="text-caption text-error">{{ loadError }}</span>
    </div>

    <div v-if="!loading && !entries.length" class="text-medium-emphasis text-body-2 py-4">
      Плановых позиций не найдено
    </div>

    <table v-else class="scp-table">
      <tbody>
        <tr v-for="entry in entries" :key="entry.key">
          <template v-if="entry.kind === 'header'">
            <td :colspan="planToRequest.active.value ? 5 : 4" class="scp-header" :style="{ paddingLeft: `${(entry.level - 1) * 20 + 8}px` }">
              <v-checkbox-btn
                v-if="planToRequest.active.value"
                :model-value="headerCheckState(entry).all"
                :indeterminate="headerCheckState(entry).some && !headerCheckState(entry).all"
                density="compact" class="mr-1"
                @update:model-value="(v: boolean | null) => toggleHeader(entry, !!v)"
              />
              <span class="font-weight-medium">{{ entry.label }}</span>
              <span class="text-caption text-medium-emphasis ml-2">{{ entry.count }} поз. · {{ formatMoney(entry.sum) }}</span>
            </td>
          </template>
          <template v-else>
            <td v-if="planToRequest.active.value" class="scp-td-check">
              <v-checkbox-btn
                :model-value="feoLevel5.isPlannedItemSelected(entry.item.id)"
                :disabled="planToRequest.isPlannedItemFullyTaken(entry.item.id)"
                density="compact"
                @update:model-value="feoLevel5.togglePlannedItemSelected(entry.item.id)"
              />
            </td>
            <td class="scp-td-name">
              {{ entry.item.name }}
              <div class="text-caption text-medium-emphasis">{{ entry.item.feo_category_name || '—' }}</div>
            </td>
            <td class="scp-td-qty text-right">{{ entry.item.quantity ?? '—' }} {{ entry.item.unit || '' }}</td>
            <td class="scp-td-sum text-right">{{ formatMoney(entry.item.amount) }}</td>
            <td class="scp-td-badge">
              <v-chip v-if="planToRequest.isPlannedItemFullyTaken(entry.item.id)" size="x-small" color="success" variant="flat">закуплено полностью</v-chip>
            </td>
          </template>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { formatMoney } from '@/utils/formatMoney'
import { matchesItemTypeFilter } from '@/utils/itemTypeKind'
import { useFeoTreePrefs } from '@/composables/subsidies/useFeoTreePrefs'
import { useFeoLevel5Api } from '@/composables/subsidies/useFeoLevel5'
import { usePlanToRequest } from '@/composables/subsidies/usePlanToRequest'
import { buildPlannedGroupEntries, type FeoPlannedGroupEntry } from '@/composables/subsidies/useFeoPlannedItemGroups'
import type { FeoPlannedItem } from '@/composables/subsidies/types'

const props = defineProps<{ subsidyId: number | null }>()

const feoTreePrefs = useFeoTreePrefs()
const feoLevel5 = useFeoLevel5Api()
const planToRequest = usePlanToRequest()

const loading = ref(false)
const loadError = ref<string | null>(null)
const plannedItems = ref<FeoPlannedItem[]>([])

async function load(subsidyId: number | null) {
  if (subsidyId == null) { plannedItems.value = []; return }
  loading.value = true
  loadError.value = null
  try {
    const res = await apiFetch<{ planned: FeoPlannedItem[] }>(`/feo-planned-items/comparison?subsidy_id=${subsidyId}`)
    plannedItems.value = res.planned || []
  } catch (e: any) {
    plannedItems.value = []
    loadError.value = e?.payload?.detail || e?.message || 'Не удалось загрузить плановые позиции субсидии'
  } finally {
    loading.value = false
  }
}

watch(() => props.subsidyId, (id) => { void load(id) }, { immediate: true })

// Жалоба владельца (28.10.2026): после правки плана в обычном дереве (PUT/POST/
// DELETE плановой позиции) эта панель должна подхватить изменения без ручной
// перезагрузки страницы — тот же сигнал feoPlanChangeBus, что уже перегружает
// feoResiduals у usePlanToRequest.ts (Правило №6, второй bus не заводим).
import { onFeoPlanChanged } from '@/composables/subsidies/feoPlanChangeBus'
onFeoPlanChanged(() => { void load(props.subsidyId) })

// Фильтр «Все/Товары/Услуги» применяется ДО группировки — отфильтрованные
// позиции не попадают ни в список, ни в суммы заголовков групп.
const filteredItems = computed(() =>
  plannedItems.value.filter(p => matchesItemTypeFilter(p.item_type_effective, feoTreePrefs.feoItemTypeFilter.value)),
)

// Всегда 'category_type' (категория → вид → позиции) — см. докстринг компонента.
const entries = computed<FeoPlannedGroupEntry[]>(() => buildPlannedGroupEntries(filteredItems.value, 'category_type'))

// ── Выбор группы целиком (владелец: «выбрать позиции галочками... и создать
// ОДНУ заявку») — та же трактовка «остатка», что и usePlanToRequest.ts
// (isPlannedItemFullyTaken, Правило №6): группа отмечает только позиции, у
// которых остаток > 0 (полностью закупленные не предлагаются к повторному
// выбору). Сами id собираются из entries (плоский список), не из
// plannedItems напрямую — группа должна отражать РЕАЛЬНО отрисованные строки.
function idsOfGroup(headerEntry: FeoPlannedGroupEntry & { kind: 'header' }): number[] {
  const ids: number[] = []
  let collecting = false
  for (const e of entries.value) {
    if (e.kind === 'header') {
      if (e.key === headerEntry.key) { collecting = true; continue }
      // Заголовок того же или более верхнего уровня завершает группу.
      if (collecting && e.level <= headerEntry.level) break
      continue
    }
    if (collecting) ids.push(e.item.id)
  }
  return ids
}

function eligibleIdsOfGroup(headerEntry: FeoPlannedGroupEntry & { kind: 'header' }): number[] {
  return idsOfGroup(headerEntry).filter(id => !planToRequest.isPlannedItemFullyTaken(id))
}

function headerCheckState(entry: FeoPlannedGroupEntry): { all: boolean; some: boolean } {
  if (entry.kind !== 'header') return { all: false, some: false }
  const eligible = eligibleIdsOfGroup(entry)
  if (!eligible.length) return { all: false, some: false }
  const selectedCount = eligible.filter(id => feoLevel5.isPlannedItemSelected(id)).length
  return { all: selectedCount === eligible.length, some: selectedCount > 0 }
}

function toggleHeader(entry: FeoPlannedGroupEntry, on: boolean) {
  if (entry.kind !== 'header') return
  const eligible = eligibleIdsOfGroup(entry)
  if (!eligible.length) return
  const s = new Set(feoLevel5.selectedPlannedItemIds.value)
  for (const id of eligible) { if (on) s.add(id); else s.delete(id) }
  feoLevel5.selectedPlannedItemIds.value = s
}
</script>

<style scoped>
.subsidy-category-panel { margin: 8px 0; }
.scp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.scp-table td { padding: 4px 8px; border-bottom: 1px solid var(--crm-border); vertical-align: middle; }
.scp-header { background: var(--crm-surface-variant, rgba(0, 150, 136, 0.06)); }
.scp-td-check { width: 36px; }
.scp-td-qty { white-space: nowrap; width: 110px; }
.scp-td-sum { white-space: nowrap; width: 120px; font-weight: 500; }
.scp-td-badge { width: 160px; }
</style>
