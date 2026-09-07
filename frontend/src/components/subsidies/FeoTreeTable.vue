<template>
  <div v-if="ctx.feoCategories.value.length === 0" class="feo-empty">
    <v-icon icon="mdi-folder-off" size="40" color="grey-lighten-2" />
    <div class="text-caption text-medium-emphasis mt-2">Нет категорий ФЭО</div>
  </div>

  <!-- FEO table with D&D, inline edit, total row -->
  <div v-else ref="feoTableAreaEl" class="feo-table-wrap">
    <table class="feo-table">
      <thead>
        <tr>
          <th class="feo-th feo-th-name" :style="ctx.feoResize.resizeStyle('name')">
            Наименование
            <span class="col-resize-handle" @mousedown="ctx.feoResize.onResizeStart($event, 'name')"></span>
          </th>
          <th class="feo-th feo-th-num" :style="ctx.feoResize.resizeStyle('budget')">
            <div>Количество и<br>финансирование по ФЭО</div>
            <span class="col-resize-handle" @mousedown="ctx.feoResize.onResizeStart($event, 'budget')"></span>
          </th>
          <th class="feo-th feo-th-num" :style="ctx.feoResize.resizeStyle('qty')">
            <div>ПЛАНОВОЕ<br>КОЛ-ВО</div>
            <div class="feo-residual-toggle">
              <span
                :class="ctx.plannedQtyBase.value === 'all' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Ручной план ФЭО + позиции заявок в плане закупок"
                @click.stop="ctx.plannedQtyBase.value = 'all'"
              >все</span>
              <span
                :class="ctx.plannedQtyBase.value === 'manual' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Только ручной план ФЭО"
                @click.stop="ctx.plannedQtyBase.value = 'manual'"
              >ручные</span>
              <span
                :class="ctx.plannedQtyBase.value === 'requests' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Только позиции заявок со статусом «План закупок» и дальше"
                @click.stop="ctx.plannedQtyBase.value = 'requests'"
              >из заявок</span>
              <span
                :class="ctx.plannedQtyBase.value === 'purchases' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Ручной план ФЭО + позиции закупок без слияния; при раскрытии направления — папки по закупкам"
                @click.stop="ctx.plannedQtyBase.value = 'purchases'"
              >по закупкам</span>
            </div>
            <span class="col-resize-handle" @mousedown="ctx.feoResize.onResizeStart($event, 'qty')"></span>
          </th>
          <th class="feo-th feo-th-num" :style="ctx.feoResize.resizeStyle('planned')">
            <div>ПЛАНОВАЯ<br>СУММА</div>
            <div class="feo-residual-toggle">
              <span
                :class="ctx.plannedSumBase.value === 'all' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Ручной план ФЭО + позиции заявок в плане закупок"
                @click.stop="ctx.plannedSumBase.value = 'all'"
              >все</span>
              <span
                :class="ctx.plannedSumBase.value === 'manual' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Только ручной план: кол-во × стоимость за ед."
                @click.stop="ctx.plannedSumBase.value = 'manual'"
              >ручные</span>
              <span
                :class="ctx.plannedSumBase.value === 'requests' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Только позиции заявок со статусом «План закупок» и дальше"
                @click.stop="ctx.plannedSumBase.value = 'requests'"
              >из заявок</span>
              <span
                :class="ctx.plannedSumBase.value === 'purchases' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Ручной план ФЭО + позиции закупок без слияния; при раскрытии направления — папки по закупкам"
                @click.stop="ctx.plannedSumBase.value = 'purchases'"
              >по закупкам</span>
            </div>
            <span class="col-resize-handle" @mousedown="ctx.feoResize.onResizeStart($event, 'planned')"></span>
          </th>
          <th class="feo-th feo-th-num" :style="ctx.feoResize.resizeStyle('spent')"
            title="Сумма всех позиций закупок этой категории во всех статусах плана закупок (включая «План закупок»), в отличие от договорного факта"
          >
            В плане-графике
            <span class="col-resize-handle" @mousedown="ctx.feoResize.onResizeStart($event, 'spent')"></span>
          </th>
          <th class="feo-th feo-th-num" :style="ctx.feoResize.resizeStyle('residual')">
            <div>ОСТАТОК</div>
            <div class="feo-residual-toggle">
              <span
                :class="ctx.residualBase.value === 'plan' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Остаток = Плановая сумма − В плане-графике"
                @click.stop="ctx.residualBase.value = 'plan'"
              >от плановой</span>
              <span
                :class="ctx.residualBase.value === 'feo' ? 'feo-residual-opt feo-residual-opt--active' : 'feo-residual-opt'"
                title="Остаток = Финансирование по ФЭО − В плане-графике"
                @click.stop="ctx.residualBase.value = 'feo'"
              >от ФЭО</span>
            </div>
            <span class="col-resize-handle" @mousedown="ctx.feoResize.onResizeStart($event, 'residual')"></span>
          </th>
          <th class="feo-th feo-th-actions"></th>
        </tr>
      </thead>
      <tbody>
        <template v-for="node in ctx.visibleFeoNodes.value" :key="node.id">
          <FeoTreeRow :node="node" />
          <FeoLevel5Panel :node="node" />
          <template v-for="owner in (ctx.reqOwnersAfter.value[node.id] || [])" :key="`reqblk-${owner.id}`">
            <FeoReqItemsRows v-if="ctx.plannedBase.value !== 'purchases'" :owner="owner" />
            <FeoByPurchasesRows v-else :owner="owner" />
          </template>
        </template>

        <!-- Drop zone: переместить на верхний уровень -->
        <tr v-if="ctx.dragNodeId.value"
          class="feo-tr feo-drop-root"
          :class="{ 'feo-drop-target': ctx.dragOverId.value === -1 }"
          @dragover.prevent="ctx.dragOverId.value = -1"
          @dragleave="ctx.dragOverId.value = null"
          @drop.prevent="ctx.onDropToRoot"
        >
          <td colspan="6" class="feo-td text-center text-caption text-medium-emphasis" style="padding:12px">
            <v-icon icon="mdi-arrow-up-bold" size="16" class="mr-1" />
            Переместить на верхний уровень (корень)
          </td>
        </tr>

        <!-- Без категории ФЭО -->
        <tr v-if="ctx.unassignedFeo.value.amount > 0 || ctx.unassignedFeo.value.purchase_count > 0"
          class="feo-tr feo-tr--unassigned"
          style="cursor:pointer"
          title="Перейти в реестр закупок субсидии"
          @click="ctx.goToUnassignedFeoPurchases"
        >
          <td class="feo-td feo-td-name" style="padding-left:8px">
            <v-icon icon="mdi-help-circle-outline" size="16" color="#F59E0B" class="mr-1" />
            <span style="color:#F59E0B;font-weight:600">Без категории ФЭО</span>
            <div class="feo-plan-note text-medium-emphasis font-weight-regular">
              {{ ctx.unassignedFeo.value.purchase_count }} {{ ctx.unassignedFeo.value.purchase_count === 1 ? 'закупка не привязана' : 'закупок не привязаны' }}
              к категориям — распределите, иначе деньги не видны в плане
            </div>
          </td>
          <td class="feo-td feo-td-num">—</td>
          <td class="feo-td feo-td-num">—</td>
          <td class="feo-td feo-td-num" style="color:#F59E0B;font-weight:600">{{ formatCurrency(ctx.unassignedFeo.value.amount) }}</td>
          <td class="feo-td feo-td-num">—</td>
          <td class="feo-td feo-td-num">—</td>
        </tr>

        <!-- Итого -->
        <tr class="feo-tr feo-tr--total">
          <td class="feo-td feo-td-name font-weight-bold" style="padding-left:8px">ИТОГО</td>
          <td class="feo-td feo-td-num font-weight-bold">
            <span title="Сумма верхних категорий: ручное ФЭО, без него — факт (поставлено/оплачено), иначе план">
              {{ formatCurrency(ctx.totalFeoEffective.value) }}
            </span>
            <div v-if="ctx.totalFeoBudget.value !== null" class="feo-plan-note text-medium-emphasis font-weight-regular"
              title="Ручной бюджет субсидии"
            >
              бюджет {{ formatCurrency(ctx.totalFeoBudget.value) }}
            </div>
            <div v-if="ctx.totalFeoBudget.value !== null && ctx.totalFeoDiff.value > 0.005"
              class="feo-plan-note font-weight-regular" style="color:#EF4444"
              :title="`Сумма категорий ${formatCurrency(ctx.totalFeoEffective.value)} превышает бюджет субсидии ${formatCurrency(ctx.totalFeoBudget.value)}`"
            >
              лишние {{ formatCurrency(ctx.totalFeoDiff.value) }}
            </div>
            <div v-else-if="ctx.totalFeoBudget.value !== null && ctx.totalFeoDiff.value < -0.005"
              class="feo-plan-note font-weight-regular" style="color:#F59E0B"
              :title="`Сумма категорий ${formatCurrency(ctx.totalFeoEffective.value)} меньше бюджета субсидии ${formatCurrency(ctx.totalFeoBudget.value)}`"
            >
              не распределено {{ formatCurrency(-ctx.totalFeoDiff.value) }}
            </div>
          </td>
          <td class="feo-td feo-td-num font-weight-bold">
            {{ ctx.feoTree.value.reduce((acc, r) => acc + ctx.feoQtyDisplayFor(r), 0) > 0 ? ctx.feoTree.value.reduce((acc, r) => acc + ctx.feoQtyDisplayFor(r), 0) : '—' }}
          </td>
          <td class="feo-td feo-td-num font-weight-bold">
            {{ ctx.feoTree.value.reduce((acc, r) => acc + ctx.feoPlannedDisplayFor(r), 0) > 0 ? formatCurrency(ctx.feoTree.value.reduce((acc, r) => acc + ctx.feoPlannedDisplayFor(r), 0)) : '—' }}
          </td>
          <!-- Футер обязан считаться по той же шкале, что и колонка «В плане-графике» в строках. -->
          <td class="feo-td feo-td-num font-weight-bold">{{ formatCurrency(ctx.totalFeoInPlanSchedule.value) }}</td>
          <td class="feo-td feo-td-num font-weight-bold">
            {{ formatCurrency(ctx.feoTree.value.reduce((acc, r) => acc + ctx.feoResidualBaseFor(r), 0) - ctx.totalFeoInPlanSchedule.value) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
// Таблица дерева ФЭО (направления с заголовками, D&D, инлайн-редактированием,
// итоговой строкой, drop-zone, «без категории») — вынесена из SubsidiesView.vue
// (волна 5c). Строки — FeoTreeRow.vue (основная строка узла) + FeoLevel5Panel.vue
// (панель «Плановые vs Фактические») + FeoReqItemsRows.vue/FeoByPurchasesRows.vue
// (позиции «из заявок» после поддерева владельца). Формулы/состояние —
// composables/subsidies/useFeoTree*.ts (Правило №6), здесь только вёрстка +
// сборка строк.
import { watchEffect, ref } from 'vue'
import { useSubsidyDetailCtx } from '@/composables/subsidies/useSubsidyDetail'
import { formatCurrency } from '@/composables/subsidies/format'
import FeoTreeRow from './FeoTreeRow.vue'
import FeoLevel5Panel from './FeoLevel5Panel.vue'
import FeoReqItemsRows from './FeoReqItemsRows.vue'
import FeoByPurchasesRows from './FeoByPurchasesRows.vue'

const ctx = useSubsidyDetailCtx()

// ctx.feoTableArea — ref на контейнер таблицы, нужен FeoTreeToolbar.vue для
// PDF-экспорта (см. её докстринг); ref DOM-элемента не может быть создан внутри
// родителя для элемента, реально живущего в этом дочернем компоненте, поэтому
// синхронизируем через watchEffect.
const feoTableAreaEl = ref<HTMLElement | null>(null)
watchEffect(() => {
  ctx.feoTableArea.value = feoTableAreaEl.value
})
</script>

<style>
/* ── FEO Tree Table ──────────────────────────────────────────────────────
   ГЛОБАЛЬНЫЙ (не scoped) стиль — сознательно: строки дерева/панель Level 5/
   позиции «из заявок» теперь отдельные компоненты (FeoTreeRow.vue/
   FeoLevel5Panel.vue/FeoReqItemsRows.vue/FeoByPurchasesRows.vue), а scoped CSS
   одного .vue-файла не достаёт вложенные элементы ДРУГОГО компонента (только
   его корень) — до разбиения (волна 5c) все эти классы были частью ОДНОГО
   шаблона SubsidiesView.vue, где scoped прекрасно работал. Классы с префиксом
   feo- специфичны для этой фичи (риск конфликта с другими экранами минимален),
   перенесены сюда единым блоком вместе с разметкой, которую они стилизуют. */
.feo-empty {
  display: flex; flex-direction: column; align-items: center;
  padding: 32px 0; color: var(--crm-text-faint);
}
.feo-purchase-link {
  display: inline-flex; align-items: center;
  font-size: 11px; color: #0d9488;
  text-decoration: none; margin-top: 2px;
  cursor: pointer;
}
.feo-purchase-link:hover { text-decoration: underline; color: #0f766e; }

.feo-stopped-marker {
  display: inline-flex;
  align-items: center;
  font-weight: 800;
  font-size: 11px;
  letter-spacing: 0.02em;
  color: #b71c1c;
  background: #fdecea;
  border: 1.5px solid #d32f2f;
  border-radius: 4px;
  padding: 2px 8px;
}

.feo-table-wrap {
  border: 1px solid var(--crm-border-strong);
  border-radius: 8px;
  overflow-x: auto;
  overflow-y: auto;
  max-height: calc(100vh - 260px);
}
.feo-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 1100px;
}
.feo-th {
  font-size: 11px; font-weight: 600; color: var(--crm-text-muted);
  text-transform: uppercase; letter-spacing: 0.05em;
  background: var(--crm-table-header); padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid var(--crm-border-strong);
  position: sticky;
  top: 0;
  z-index: 3;
  box-shadow: inset 0 -1px 0 var(--crm-border-strong);
}
.feo-th-num { text-align: right; }
.feo-th-name { }
.feo-th-actions { width: 112px; position: sticky; right: 0; z-index: 5; }
.feo-td {
  padding: 8px 12px; border-bottom: 1px solid var(--crm-border);
  vertical-align: middle;
}
.feo-td-name { min-width: 0; }
.feo-name-inner { display: flex; align-items: center; min-width: 0; }
.feo-td-num { text-align: right; }
.feo-td-actions {
  text-align: right; white-space: nowrap; padding-left: 6px; padding-right: 6px;
  position: sticky; right: 0; z-index: 2;
  background: var(--crm-surface);
  box-shadow: inset 1px 0 0 var(--crm-border-strong);
}
.feo-actions-wrap { display: inline-flex; align-items: center; vertical-align: middle; }
.feo-actions-wrap .v-btn { width: 24px !important; height: 24px !important; }
.feo-actions-col { display: flex; flex-direction: column; align-items: center; }
.feo-actions-grid {
  display: inline-grid; grid-template-columns: repeat(2, 26px);
  justify-items: center; align-items: center;
}
.feo-td-actions .v-btn { background: transparent !important; }
.feo-tr:hover .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td-actions { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td-actions { background: var(--crm-surface-hover); }
.feo-action-slot { display: inline-flex; width: 24px; justify-content: center; vertical-align: middle; }
.feo-tr:last-child .feo-td { border-bottom: none; }
.feo-tr:hover .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1 .feo-td { background: var(--crm-surface-alt); }
.feo-tr--l1:hover .feo-td { background: var(--crm-surface-hover); }
.feo-plan-note { font-size: 10px; line-height: 1.2; white-space: nowrap; }
.feo-plan-note--link { cursor: pointer; text-decoration: none; }
.feo-plan-note--link:hover { text-decoration: underline; color: #0f766e; }
.feo-excess-culprit {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  font-size: 12px; font-weight: 700; line-height: 1.4; white-space: normal;
  color: #7f1d1d; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.45);
  border-radius: 6px; padding: 4px 8px; margin-top: 4px; max-width: 100%;
}
.feo-residual-toggle { display: flex; gap: 2px; justify-content: flex-end; margin-top: 2px; }
.feo-residual-opt {
  font-size: 9px; font-weight: 500; text-transform: none; letter-spacing: 0;
  padding: 1px 6px; border-radius: 8px; cursor: pointer;
  color: #94a3b8; border: 1px solid transparent; user-select: none;
}
.feo-residual-opt:hover { color: #475569; }
.feo-residual-opt--active { color: #0f766e; background: rgba(20,184,166,0.12); border-color: rgba(20,184,166,0.35); }
.feo-name { font-size: 13px; font-weight: 500; color: var(--crm-text); white-space: normal; word-break: break-word; min-width: 0; flex: 1; }
.feo-name--l1 { font-weight: 700; font-size: 13px; }
.feo-name--l2 { font-weight: 600; }
.feo-name--l3 { font-weight: 400; color: var(--crm-text-secondary); }
.feo-code {
  font-size: 11px; color: var(--crm-text-muted); background: var(--crm-input-bg);
  border-radius: 4px; padding: 1px 5px; font-family: monospace; white-space: nowrap;
}
.feo-appendix { font-size: 11px; color: var(--crm-text-faint); white-space: nowrap; }
.feo-amount { font-size: 13px; font-weight: 500; color: var(--crm-text); }
.feo-amount--link { cursor: pointer; text-decoration: underline dotted; }
.feo-amount--link:hover { color: #1976d2; }
.feo-amount-empty { font-size: 13px; color: var(--crm-text-faint); }
.feo-set-hint {
  font-size: 12px; color: #3B82F6; cursor: pointer; text-decoration: underline dotted;
}
.feo-set-hint:hover { color: #2563EB; }
.feo-tree-chevron { display: inline-flex; align-items: center; }
.cursor-pointer { cursor: pointer; }

/* Inline budget edit */
.feo-amount-cell { cursor: pointer; padding: 2px 4px; border-radius: 4px; display: inline-flex; align-items: center; }
.feo-amount-cell:hover { background: rgba(59,130,246,0.07); }
.feo-amount-cell--readonly { cursor: default; }
.feo-amount-cell--readonly:hover { background: none; }
.inline-input {
  border: 1px solid rgba(59,130,246,0.7); border-radius: 4px;
  padding: 2px 6px; width: 120px; text-align: right;
  font-size: 0.875rem; outline: none; background: var(--crm-surface);
  color: var(--crm-text);
}

/* Drag & Drop */
.feo-tr[draggable="true"] { cursor: grab; }
.feo-tr[draggable="true"]:active { cursor: grabbing; }
.feo-dragging { opacity: 0.45; }
.feo-dragging .feo-td { background: var(--crm-surface-alt) !important; }
.feo-drop-target .feo-td {
  background: rgba(59, 130, 246, 0.12) !important;
  outline: 2px dashed rgba(59, 130, 246, 0.6);
  outline-offset: -2px;
}
.feo-drop-root { border-top: 2px dashed var(--crm-border); transition: background 0.15s; }
.feo-drop-root.feo-drop-target .feo-td { background: rgba(59, 130, 246, 0.08) !important; }

/* Total row */
.feo-tr--total .feo-td { background: var(--crm-surface-alt); border-top: 2px solid var(--crm-border-strong); }

/* Column resize handle */
.col-resize-handle {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  z-index: 1;
}
.col-resize-handle::before {
  content: '';
  position: absolute;
  right: 3px;
  top: 20%;
  bottom: 20%;
  width: 2px;
  background: rgba(0, 0, 0, 0.18);
  border-radius: 2px;
  transition: all 0.15s ease;
}
.v-theme--dark .col-resize-handle::before {
  background: rgba(255, 255, 255, 0.22);
}
.col-resize-handle:hover::before,
.col-resize-handle:active::before {
  right: 2px;
  top: 5%;
  bottom: 5%;
  width: 3px;
  background: rgb(59, 130, 246);
}

/* ── KPI drill-down: подсветка дерева ФЭО по клику на карточку ── */
.feo-kpi-hl > .feo-td, .feo-kpi-hl > td {
  background: rgba(251,146,60,.16) !important;
  animation: feo-kpi-glow 1.4s ease-in-out infinite;
}
.feo-kpi-hl > .feo-td:first-child, .feo-kpi-hl > td:first-child { border-left: 3px solid #fb923c; }
@keyframes feo-kpi-glow {
  0%, 100% { box-shadow: inset 0 0 0 9999px rgba(251,146,60,0); }
  50%      { box-shadow: inset 0 0 0 9999px rgba(251,146,60,.14); }
}
.feo-kpi-path > .feo-td:first-child { border-left: 3px solid rgba(251,146,60,.35); }
.feo-kpi-dim  > .feo-td, .feo-kpi-dim > td { opacity: .32; filter: grayscale(.5); }
.feo-kpi-dim  > .feo-td-actions { opacity: 1; filter: none; }
.feo-kpi-banner {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--crm-text-secondary);
  background: rgba(251,146,60,.10); border: 1px solid rgba(251,146,60,.35);
  border-radius: 8px; padding: 6px 12px; margin: -8px 0 16px;
}
.feo-status-strip { display: inline-flex; align-items: center; }

/* Тёмная тема: .16/.32/.14 почти сливаются с тёмной подложкой — усиливаем контраст */
.v-theme--dark .feo-kpi-hl > .feo-td,
.v-theme--dark .feo-kpi-hl > td {
  background: rgba(251,146,60,.30) !important;
  animation-name: feo-kpi-glow-dark;
}
@keyframes feo-kpi-glow-dark {
  0%, 100% { box-shadow: inset 0 0 0 9999px rgba(251,146,60,0); }
  50%      { box-shadow: inset 0 0 0 9999px rgba(251,146,60,.22); }
}
.v-theme--dark .feo-kpi-dim > .feo-td,
.v-theme--dark .feo-kpi-dim > td { opacity: .22; }
</style>
