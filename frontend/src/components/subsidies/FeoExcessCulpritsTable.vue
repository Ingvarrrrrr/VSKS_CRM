<!-- Таблица «виновников превышения» направления ФЭО — вынесена из
     FeoCardDrillDialog.vue (Правило №5: тот файл был 626 строк). Строка —
     ЗАКУПКА (бэкенд теперь группирует позиции по закупке, excess_groups,
     см. services/excess_culprit_order.py и feo_card_drill.py), раскрытие
     строки показывает её позиции. Позиция без закупки — своя группа
     (purchase_id=null). Суммы НЕ пересчитываются на фронте (Правило №6) —
     показывается то, что прислал backend; «Итого сверх ФЭО» = excessTotal,
     сверяется с суммой превышения направления родителем (mismatch).

     Фолбэк: если backend ещё не отдаёт excess_groups (раздельная выкладка
     фронта/бэкенда, план binary-crunching-island.md) — рисуется старая
     плоская таблица по items (как было до этого плана), чтобы фронт не
     ломался, пока бэкенд не выехал. -->
<template>
  <div>
    <v-alert v-if="batchNote" type="info" variant="tonal" density="compact" class="mb-2 text-caption">
      {{ batchNote.message }}
    </v-alert>

    <v-alert v-if="mismatch" type="warning" variant="tonal" density="compact" class="mb-2 text-caption">
      Σ «сверх ФЭО» по виновникам ({{ formatCurrency(excessTotal) }}) отличается от превышения
      направления ({{ formatCurrency(rowExcessAmount) }}) — часть превышения пришла не из плановых
      позиций этого типа (замещение заказом/договором или «пол»), смотрите «Показать весь состав».
    </v-alert>

    <!-- Новый формат — строки по закупкам, раскрытие → позиции закупки -->
    <v-table v-if="groups && groups.length" density="compact" class="mt-1" style="min-width:820px; background:transparent">
      <thead>
        <tr>
          <th class="px-2" />
          <th class="px-2">№ закупки</th>
          <th class="px-2">Реестровый №</th>
          <th class="px-2">Предмет</th>
          <th class="px-2">Категория ФЭО</th>
          <th class="px-2">Тип</th>
          <th class="px-2">Дата добавления в план</th>
          <th class="text-right px-2">Сумма</th>
          <th class="text-right px-2">в т.ч. сверх ФЭО</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(g, gIdx) in groups" :key="groupKey(g, gIdx)">
          <tr class="feo-excess-group-row" @click="toggleGroup(groupKey(g, gIdx))">
            <td class="px-2">
              <v-icon size="16">{{ expandedGroups.has(groupKey(g, gIdx)) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
            </td>
            <td class="px-2 text-caption">{{ g.purchase_number ?? g.purchase_id ?? '—' }}</td>
            <td class="px-2 text-caption">{{ g.registry_number || '—' }}</td>
            <td class="px-2 py-1 text-caption" style="max-width:220px; white-space:normal">{{ g.subject || '—' }}</td>
            <td class="px-2 text-caption" style="max-width:200px; white-space:normal">{{ g.category_path || '—' }}</td>
            <td class="px-2 text-caption">{{ g.kind_label || '—' }}</td>
            <td class="px-2 text-caption text-medium-emphasis">{{ formatDate(g.date) }}</td>
            <td class="text-right px-2 text-caption">{{ formatCurrency(g.amount) }}</td>
            <td class="text-right px-2 text-caption font-weight-medium text-error">{{ formatCurrency(g.over_amount) }}</td>
          </tr>
          <tr v-if="expandedGroups.has(groupKey(g, gIdx))">
            <td colspan="9" class="pa-0" style="border-top:none">
              <v-table density="compact" class="ma-2" style="background: rgba(146,64,14,0.04)">
                <thead>
                  <tr>
                    <th class="px-2 text-caption">Позиция</th>
                    <th class="text-right px-2 text-caption">Сумма</th>
                    <th class="text-right px-2 text-caption">Сверх ФЭО</th>
                    <th class="px-2 text-caption">Дата изменения в плане</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="it in g.items" :key="it.planned_item_id">
                    <td class="px-2 py-1 text-caption" style="max-width:260px; white-space:normal">{{ it.name || '—' }}</td>
                    <td class="text-right px-2 text-caption">{{ formatCurrency(it.amount) }}</td>
                    <td class="text-right px-2 text-caption text-error">{{ formatCurrency(it.over_amount) }}</td>
                    <td class="px-2 text-caption text-medium-emphasis">{{ formatDate(it.plan_changed_at) }}</td>
                  </tr>
                </tbody>
              </v-table>
            </td>
          </tr>
        </template>
      </tbody>
      <tfoot>
        <tr>
          <td colspan="7" class="px-2 text-right font-weight-medium">Итого сверх ФЭО:</td>
          <td />
          <td class="text-right px-2 font-weight-bold text-error">{{ formatCurrency(excessTotal) }}</td>
        </tr>
      </tfoot>
    </v-table>

    <!-- Пачка: groups пуст (виновника не называем), но items тоже нет —
         только плашка выше, без пустой таблицы. -->
    <div v-else-if="!items || !items.length" class="text-caption text-medium-emphasis">
      Весь состав — по ссылке «Показать весь состав».
    </div>

    <!-- Фолбэк — старый плоский список позиций (backend ещё без excess_groups) -->
    <v-table v-else density="compact" class="mt-1" style="min-width:760px; background:transparent">
      <thead>
        <tr>
          <th class="px-2">№ закупки</th>
          <th class="px-2">Предмет</th>
          <th class="px-2">Категория ФЭО</th>
          <th class="px-2">Позиция</th>
          <th class="px-2">Тип</th>
          <th class="px-2">Дата добавления</th>
          <th class="text-right px-2">Сумма</th>
          <th class="text-right px-2">в т.ч. сверх ФЭО</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="it in items" :key="'item-' + (it.planned_item_id ?? it.name)">
          <td class="px-2 text-caption">{{ it.purchase_number || it.purchase_id || '—' }}</td>
          <td class="px-2 py-1 text-caption" style="max-width:220px; white-space:normal">{{ it.subject || it.name || '—' }}</td>
          <td class="px-2 text-caption" style="max-width:220px; white-space:normal">{{ it.category_path || '—' }}</td>
          <td class="px-2 py-1 text-caption" style="max-width:220px; white-space:normal">{{ it.name || '—' }}</td>
          <td class="px-2 text-caption">{{ it.item_type || '—' }}</td>
          <td class="px-2 text-caption text-medium-emphasis">{{ formatDate(it.created_at) }}</td>
          <td class="text-right px-2 text-caption">{{ formatCurrency(it.amount) }}</td>
          <td class="text-right px-2 text-caption font-weight-medium text-error">{{ formatCurrency(it.over_amount) }}</td>
        </tr>
      </tbody>
      <tfoot v-if="items && items.length">
        <tr>
          <td colspan="6" class="px-2 text-right font-weight-medium">Итого сверх ФЭО:</td>
          <td />
          <td class="text-right px-2 font-weight-bold text-error">{{ formatCurrency(excessTotal) }}</td>
        </tr>
      </tfoot>
    </v-table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { formatCurrency } from '@/composables/subsidies/format'

export interface ExcessGroupItem {
  planned_item_id: number
  name: string | null
  amount: number
  over_amount: number
  plan_changed_at: string | null
}
export interface ExcessGroup {
  purchase_id: number | null
  purchase_number: number | string | null
  registry_number: string | null
  subject: string | null
  category_path: string | null
  kind_label: string | null
  date: string | null
  amount: number
  over_amount: number
  items: ExcessGroupItem[]
}
export interface ExcessBatchNote {
  date: string
  count: number
  message: string
}
// Фолбэк-формат (как было до этого плана, см. DirectionExcessItem в
// FeoCardDrillDialog.vue) — та же форма, объявлена здесь, чтобы компонент
// не зависел от типов диалога.
export interface LegacyExcessItem {
  planned_item_id: number
  name: string | null
  amount: number
  over_amount: number
  created_at: string | null
  purchase_id: number | null
  purchase_number: string | number | null
  subject: string | null
  category_path: string | null
  item_type: string | null
}

const props = defineProps<{
  groups?: ExcessGroup[] | null
  items?: LegacyExcessItem[]
  excessTotal: number
  rowExcessAmount: number
  batchNote?: ExcessBatchNote | null
}>()

const expandedGroups = ref<Set<string>>(new Set())
function groupKey(g: ExcessGroup, idx: number): string {
  return `${g.purchase_id ?? 'none'}-${idx}`
}
function toggleGroup(key: string) {
  const next = new Set(expandedGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedGroups.value = next
}

const mismatch = computed(() => Math.abs((props.excessTotal || 0) - Math.abs(props.rowExcessAmount)) > 0.5)

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('ru-RU')
}
</script>

<style scoped>
.feo-excess-group-row {
  cursor: pointer;
}
.feo-excess-group-row:hover {
  background: rgba(146, 64, 14, 0.08);
}
</style>
